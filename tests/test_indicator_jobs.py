"""Tests for scheduled deterministic indicator collection jobs."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from apscheduler.schedulers.background import BackgroundScheduler

from duzman.collectors import MarketDataSnapshot, OHLCVRecord
from duzman.scheduler import indicator_jobs
from duzman.scheduler.indicator_jobs import (
    HOURLY_INDICATOR_COLLECTION_JOB_ID,
    collect_indicators_job,
    register_hourly_indicator_collection_job,
)


class FakeSession:
    """Minimal session fake for indicator job tests."""

    def __init__(self) -> None:
        self.committed = False
        self.closed = False

    def commit(self) -> None:
        """Record commit calls without touching a database."""
        self.committed = True

    def close(self) -> None:
        """Record close calls without touching a database."""
        self.closed = True


class FakeIndicatorRepository:
    """Capture indicator records passed by the scheduler job."""

    def __init__(self) -> None:
        self.records = []
        self.sessions: list[FakeSession] = []

    async def save_indicators(self, session, records):
        """Store records in memory and return the inserted count."""
        self.sessions.append(session)
        self.records = list(records)
        return len(records)


class FakeBinanceCollector:
    """Return deterministic candles and spot prices without network access."""

    def __init__(self, failing_assets: set[str] | None = None, empty_ohlcv: bool = False) -> None:
        self.failing_assets = failing_assets or set()
        self.empty_ohlcv = empty_ohlcv

    async def fetch_ohlcv(self, symbol: str, interval: str, limit: int = 100):
        """Return deterministic OHLCV data for indicator calculations."""
        if symbol in self.failing_assets:
            raise RuntimeError(f"{symbol} unavailable")
        if self.empty_ohlcv:
            return []
        return _candles(symbol, interval, limit)

    async def fetch_tickers(self, symbols: list[str]):
        """Return deterministic spot snapshots for premium/discount."""
        return [
            MarketDataSnapshot(
                source="binance",
                asset=symbol,
                quote_currency="USDT",
                price_usd=Decimal("100"),
                ts=datetime(2026, 5, 16, 12, 23, tzinfo=timezone.utc),
                raw_payload={"symbol": f"{symbol}USDT"},
            )
            for symbol in symbols
        ]


class FakeBybitCollector:
    """Return deterministic mark prices without network access."""

    async def fetch_mark_prices(self, symbols: list[str]):
        """Return deterministic mark prices for premium/discount."""
        return [{"asset": symbol, "mark_price": Decimal("101")} for symbol in symbols]


@pytest.mark.asyncio
async def test_collect_indicators_job_happy_path_saves_all_records():
    """Happy path should compute all deterministic indicators for six assets."""
    session = FakeSession()
    repository = FakeIndicatorRepository()

    inserted_count = await collect_indicators_job(
        session_factory=lambda: session,
        binance_collector=FakeBinanceCollector(),
        bybit_collector=FakeBybitCollector(),
        repository=repository,
    )

    assert inserted_count == 60
    assert len(repository.records) == 60
    assert session.committed is True
    assert session.closed is True
    assert {record.asset for record in repository.records} == {"BTC", "ETH", "SOL", "SUI", "TON", "UNI"}
    assert {"rsi", "stochastic_k", "stochastic_d", "volatility_24h", "premium_discount"}.issubset(
        {record.indicator_type for record in repository.records}
    )


@pytest.mark.asyncio
async def test_collect_indicators_job_isolates_one_failed_asset():
    """A failed asset should not prevent other assets from being persisted."""
    repository = FakeIndicatorRepository()

    inserted_count = await collect_indicators_job(
        session_factory=FakeSession,
        binance_collector=FakeBinanceCollector(failing_assets={"SOL"}),
        bybit_collector=FakeBybitCollector(),
        repository=repository,
    )

    assert inserted_count == 50
    assert "SOL" not in {record.asset for record in repository.records}
    assert {"BTC", "ETH", "SUI", "TON", "UNI"} == {record.asset for record in repository.records}


@pytest.mark.asyncio
async def test_collect_indicators_job_skips_none_indicator_values(monkeypatch):
    """None indicator outputs should not create database records."""
    repository = FakeIndicatorRepository()
    monkeypatch.setattr(indicator_jobs, "compute_rsi", lambda candles: None)

    inserted_count = await collect_indicators_job(
        session_factory=FakeSession,
        binance_collector=FakeBinanceCollector(),
        bybit_collector=FakeBybitCollector(),
        repository=repository,
    )

    assert inserted_count == 36
    assert "rsi" not in {record.indicator_type for record in repository.records}


@pytest.mark.asyncio
async def test_collect_indicators_job_skips_empty_ohlcv_but_keeps_premium():
    """Empty OHLCV should skip candle indicators while preserving premium records."""
    repository = FakeIndicatorRepository()

    inserted_count = await collect_indicators_job(
        session_factory=FakeSession,
        binance_collector=FakeBinanceCollector(empty_ohlcv=True),
        bybit_collector=FakeBybitCollector(),
        repository=repository,
    )

    assert inserted_count == 6
    assert {record.indicator_type for record in repository.records} == {"premium_discount"}


def test_register_hourly_indicator_collection_job_does_not_start_scheduler():
    """Registering the indicator job should not start a scheduler daemon."""
    scheduler = BackgroundScheduler()

    register_hourly_indicator_collection_job(scheduler, lambda: None)
    jobs = scheduler.get_jobs()

    assert scheduler.running is False
    assert len(jobs) == 1
    assert jobs[0].id == HOURLY_INDICATOR_COLLECTION_JOB_ID
    assert "minute='23'" in str(jobs[0].trigger)


def _candles(asset: str, interval: str, limit: int) -> list[OHLCVRecord]:
    base_time = datetime(2026, 5, 16, 12, 23, tzinfo=timezone.utc)
    return [
        OHLCVRecord(
            ts=base_time + timedelta(hours=index),
            asset=asset,
            exchange="binance",
            interval=interval,
            open=Decimal("100") + Decimal(index),
            high=Decimal("103") + Decimal(index),
            low=Decimal("98") + Decimal(index),
            close=Decimal("101") + Decimal(index),
            volume=Decimal("1"),
            quote_volume=Decimal("100"),
        )
        for index in range(limit)
    ]
