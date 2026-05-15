from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from duzman.collectors import MarketDataSnapshot
from duzman.db.models import Asset, PriceSnapshot, SourceHealthCheck
from duzman.runtime.market_data_scheduler import (
    build_market_data_scheduler,
    run_market_data_scheduler_forever,
)
from duzman.scheduler.market_data_jobs import HOURLY_MARKET_DATA_INGESTION_JOB_ID


class FakePublicMarketDataFetcher:
    """Runtime test fetcher that returns deterministic public market snapshots."""

    def fetch_binance_ticker(
        self, symbol: str, collected_at: datetime | None = None
    ) -> MarketDataSnapshot:
        asset_symbol = symbol.removesuffix("USDT")
        return MarketDataSnapshot(
            source="binance",
            symbol=asset_symbol,
            quote_currency="USDT",
            price=Decimal("67123.45") if asset_symbol == "BTC" else Decimal("3123.45"),
            collected_at=collected_at or datetime.now(timezone.utc),
            raw_payload={"symbol": symbol},
        )

    def fetch_coingecko_market(
        self, coin_id: str, collected_at: datetime | None = None
    ) -> MarketDataSnapshot:
        symbol = {"bitcoin": "BTC", "ethereum": "ETH"}[coin_id]
        return MarketDataSnapshot(
            source="coingecko",
            symbol=symbol,
            quote_currency="USD",
            price=Decimal("67120.01") if symbol == "BTC" else Decimal("3120.01"),
            collected_at=collected_at or datetime.now(timezone.utc),
            raw_payload={"id": coin_id},
        )


def _session_factory() -> tuple[Callable[[], Session], Session]:
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
    return lambda: session, session


def test_runtime_module_import_has_no_side_effects():
    """Importing the runtime module should not build or start a scheduler."""
    import duzman.runtime.market_data_scheduler as runtime_module

    assert callable(runtime_module.build_market_data_scheduler)
    assert callable(runtime_module.run_market_data_scheduler_forever)


def test_build_market_data_scheduler_registers_job_without_starting():
    """The scheduler builder should register the hourly job and leave it stopped."""
    session_factory, _ = _session_factory()

    scheduler = build_market_data_scheduler(
        session_factory=session_factory,
        fetcher_factory=FakePublicMarketDataFetcher,
    )
    jobs = scheduler.get_jobs()

    assert scheduler.running is False
    assert len(jobs) == 1
    assert jobs[0].id == HOURLY_MARKET_DATA_INGESTION_JOB_ID
    assert "minute='17'" in str(jobs[0].trigger)


def test_registered_runtime_job_can_run_with_injected_offline_dependencies():
    """The registered job should run with fake fetchers and an offline DB."""
    session_factory, session = _session_factory()
    scheduler = build_market_data_scheduler(
        session_factory=session_factory,
        fetcher_factory=FakePublicMarketDataFetcher,
    )
    job = scheduler.get_jobs()[0]

    result = job.func()

    snapshots = list(session.scalars(select(PriceSnapshot)))
    health_checks = list(session.scalars(select(SourceHealthCheck)))

    assert result.snapshots_created == 4
    assert result.health_checks_created == 2
    assert {snapshot.source for snapshot in snapshots} == {"binance", "coingecko"}
    assert {health.source for health in health_checks} == {"binance", "coingecko"}


def test_runtime_forever_configures_logging_only_when_explicitly_called(monkeypatch):
    """The blocking runtime path should configure logging only during explicit run."""
    import duzman.runtime.market_data_scheduler as runtime_module

    calls: list[str] = []

    class FakeBlockingScheduler:
        def __init__(self, timezone):
            self.timezone = timezone

        def start(self):
            calls.append("start")
            raise RuntimeError("stop test scheduler")

    def fake_build_market_data_scheduler(**kwargs):
        calls.append("build")
        return kwargs["scheduler"]

    monkeypatch.setattr(runtime_module, "configure_logging", lambda: calls.append("configure"))
    monkeypatch.setattr(runtime_module, "BlockingScheduler", FakeBlockingScheduler)
    monkeypatch.setattr(
        runtime_module,
        "build_market_data_scheduler",
        fake_build_market_data_scheduler,
    )

    try:
        run_market_data_scheduler_forever(
            session_factory=lambda: None,
            fetcher_factory=FakePublicMarketDataFetcher,
        )
    except RuntimeError as exc:
        assert str(exc) == "stop test scheduler"

    assert calls == ["configure", "build", "start"]
