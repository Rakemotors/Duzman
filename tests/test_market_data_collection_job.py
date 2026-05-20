from datetime import datetime, timezone
from decimal import Decimal
import logging

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from duzman.collectors import MarketDataPayloadError, MarketDataSnapshot
from duzman.db.models import Asset, PriceSnapshot, SourceHealthCheck
from duzman.repositories import SOURCE_HEALTH_FAILED, SOURCE_HEALTH_OK
from duzman.services import MarketDataCollectionJob


def _sqlite_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    PriceSnapshot.__table__.create(engine)
    SourceHealthCheck.__table__.create(engine)
    session = Session(engine)
    session.add_all(
        [
            Asset(symbol="BTC", name="Bitcoin"),
            Asset(symbol="ETH", name="Ethereum"),
        ]
    )
    session.commit()
    return session


class FakePublicMarketDataFetcher:
    """Deterministic fetcher fake for collection-job tests."""

    def __init__(self, fail_sources: set[str] | None = None) -> None:
        self.fail_sources = fail_sources or set()

    def fetch_binance_ticker(
        self, symbol: str, collected_at: datetime | None = None
    ) -> MarketDataSnapshot:
        if "binance" in self.fail_sources:
            raise RuntimeError("binance unavailable")
        asset_symbol = symbol.removesuffix("USDT")
        return MarketDataSnapshot(
            source="binance",
            asset=asset_symbol,
            quote_currency="USDT",
            price_usd=Decimal("67123.45") if asset_symbol == "BTC" else Decimal("3123.45"),
            ts=collected_at or datetime.now(timezone.utc),
            raw_payload={"symbol": symbol},
        )

    def fetch_coingecko_market(
        self, coin_id: str, collected_at: datetime | None = None
    ) -> MarketDataSnapshot:
        if "coingecko" in self.fail_sources:
            raise RuntimeError("coingecko unavailable")
        symbol = {"bitcoin": "BTC", "ethereum": "ETH"}[coin_id]
        return MarketDataSnapshot(
            source="coingecko",
            asset=symbol,
            quote_currency="USD",
            price_usd=Decimal("67120.01") if symbol == "BTC" else Decimal("3120.01"),
            ts=collected_at or datetime.now(timezone.utc),
            raw_payload={"id": coin_id},
        )


class MalformedBinanceFetcher(FakePublicMarketDataFetcher):
    """Fetcher fake that simulates parser rejection for Binance."""

    def fetch_binance_ticker(
        self, symbol: str, collected_at: datetime | None = None
    ) -> MarketDataSnapshot:
        raise MarketDataPayloadError("missing lastPrice")


def test_collection_job_persists_successful_binance_and_coingecko_snapshots():
    """A full successful cycle should persist snapshots and ok health checks."""
    session = _sqlite_session()
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)
    job = MarketDataCollectionJob(session=session, fetcher=FakePublicMarketDataFetcher())

    result = job.run(collected_at=collected_at)

    snapshots = list(session.scalars(select(PriceSnapshot)))
    health_checks = list(session.scalars(select(SourceHealthCheck)))

    assert result.attempted_sources == ("binance", "coingecko")
    assert result.successful_sources == ("binance", "coingecko")
    assert result.failed_sources == ()
    assert result.snapshots_created == 4
    assert result.health_checks_created == 2
    assert {snapshot.source for snapshot in snapshots} == {"binance", "coingecko"}
    assert {health.status for health in health_checks} == {SOURCE_HEALTH_OK}


def test_collection_job_logs_cycle_and_source_success_without_raw_payloads(caplog):
    """Collection logs should expose event summaries without raw payload bodies."""
    session = _sqlite_session()
    job = MarketDataCollectionJob(session=session, fetcher=FakePublicMarketDataFetcher())

    caplog.set_level(logging.INFO)
    result = job.run()

    assert result.snapshots_created == 4
    assert "collection_cycle_started" in caplog.text
    assert "source_collection_succeeded source=binance" in caplog.text
    assert "source_collection_succeeded source=coingecko" in caplog.text
    assert "collection_cycle_completed" in caplog.text
    assert "raw_payload" not in caplog.text
    assert "lastPrice" not in caplog.text


def test_collection_job_partial_failure_keeps_successful_source_snapshots():
    """A failed source should not prevent successful source persistence."""
    session = _sqlite_session()
    job = MarketDataCollectionJob(
        session=session,
        fetcher=FakePublicMarketDataFetcher(fail_sources={"coingecko"}),
    )

    result = job.run()

    snapshots = list(session.scalars(select(PriceSnapshot)))
    health_by_source = {
        health.source: health.status
        for health in session.scalars(select(SourceHealthCheck))
    }

    assert result.successful_sources == ("binance",)
    assert result.failed_sources == ("coingecko",)
    assert result.snapshots_created == 2
    assert result.errors == {"coingecko": "coingecko unavailable"}
    assert {snapshot.source for snapshot in snapshots} == {"binance"}
    assert health_by_source == {
        "binance": SOURCE_HEALTH_OK,
        "coingecko": SOURCE_HEALTH_FAILED,
    }


def test_collection_job_logs_partial_failure(caplog):
    """Partial failure logs should identify the failed source and safe error."""
    session = _sqlite_session()
    job = MarketDataCollectionJob(
        session=session,
        fetcher=FakePublicMarketDataFetcher(fail_sources={"coingecko"}),
    )

    caplog.set_level(logging.INFO)
    result = job.run()

    assert result.failed_sources == ("coingecko",)
    assert "source_collection_succeeded source=binance" in caplog.text
    assert "source_collection_failed source=coingecko" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "safe_error_message=coingecko unavailable" in caplog.text


def test_collection_job_malformed_payload_does_not_persist_bad_data():
    """Malformed source data should record failed health and persist no snapshots."""
    session = _sqlite_session()
    job = MarketDataCollectionJob(
        session=session,
        fetcher=MalformedBinanceFetcher(fail_sources={"coingecko"}),
    )

    result = job.run()

    snapshot_count = session.scalar(select(func.count()).select_from(PriceSnapshot))
    health_by_source = {
        health.source: health.status
        for health in session.scalars(select(SourceHealthCheck))
    }

    assert result.successful_sources == ()
    assert result.failed_sources == ("binance", "coingecko")
    assert result.snapshots_created == 0
    assert "lastPrice" in result.errors["binance"]
    assert snapshot_count == 0
    assert health_by_source == {
        "binance": SOURCE_HEALTH_FAILED,
        "coingecko": SOURCE_HEALTH_FAILED,
    }
