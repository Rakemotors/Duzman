"""Offline tests for CoinGlass liquidation runtime jobs."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from duzman.collectors.records import HeatmapBucketRecord, LiquidationRecord
from duzman.db.models import (
    Asset,
    Liquidation,
    LiquidationHeatmap,
    PriceSnapshot,
    SourceHealthCheck,
)
from duzman.runtime.coinglass_jobs import (
    collect_heatmaps_once,
    collect_liquidations_once,
)


class _FakeLiquidationCollector:
    """Return deterministic liquidation records for runtime tests."""

    def __init__(self, health_recorder) -> None:
        self.health_recorder = health_recorder

    async def fetch_liquidations_1h(self, asset: str):
        """Return one fake liquidation record and mark source health."""
        self.health_recorder.mark_success("coinglass")
        return LiquidationRecord(
            ts=datetime(2026, 5, 16, 12, 18, tzinfo=timezone.utc),
            asset=asset,
            longs_1h_usd=Decimal("10"),
            shorts_1h_usd=Decimal("20"),
            longs_24h_usd=Decimal("100"),
            shorts_24h_usd=Decimal("200"),
        )


class _FakeHeatmapCollector:
    """Return deterministic heatmap buckets for runtime tests."""

    def __init__(self, health_recorder, price_provider) -> None:
        self.health_recorder = health_recorder
        self.price_provider = price_provider
        self.calls: list[tuple[str, str]] = []

    async def fetch_heatmap(self, asset: str, timeframe: str):
        """Return one fake heatmap bucket when a latest price exists."""
        self.calls.append((asset, timeframe))
        if self.price_provider(asset) is None:
            return []
        self.health_recorder.mark_success("coinglass")
        return [
            HeatmapBucketRecord(
                ts=datetime(2026, 5, 16, 12, 18, tzinfo=timezone.utc),
                asset=asset,
                timeframe=timeframe,
                price_low=Decimal("90000"),
                price_high=Decimal("91000"),
                liquidation_volume_usd=Decimal("123.45"),
            )
        ]


@pytest.mark.asyncio
async def test_collect_liquidations_once_inserts_records():
    """Runtime liquidation job should persist one row per enabled asset."""
    session = _sqlite_session(include_prices=True)

    inserted_count = await collect_liquidations_once(
        session_factory=lambda: session,
        collector_factory=_FakeLiquidationCollector,
    )

    rows = list(session.scalars(select(Liquidation)))
    assert inserted_count == 3
    assert {row.asset for row in rows} == {"BTC", "ETH", "SOL"}
    assert rows[0].longs_liquidated_1h_usd == Decimal("10.00")


@pytest.mark.asyncio
async def test_collect_heatmaps_once_replaces_buckets_for_btc_eth():
    """Runtime heatmap job should replace buckets for BTC/ETH timeframes."""
    session = _sqlite_session(include_prices=True)

    inserted_count = await collect_heatmaps_once(
        session_factory=lambda: session,
        collector_factory=_FakeHeatmapCollector,
    )

    rows = list(session.scalars(select(LiquidationHeatmap)))
    assert inserted_count == 4
    assert len(rows) == 4
    assert {(row.asset, row.timeframe) for row in rows} == {
        ("BTC", "24h"),
        ("BTC", "7d"),
        ("ETH", "24h"),
        ("ETH", "7d"),
    }


@pytest.mark.asyncio
async def test_collect_heatmaps_once_skips_assets_without_price_snapshots():
    """Heatmap job should not persist buckets when current prices are missing."""
    session = _sqlite_session(include_prices=False)

    inserted_count = await collect_heatmaps_once(
        session_factory=lambda: session,
        collector_factory=_FakeHeatmapCollector,
    )

    assert inserted_count == 0
    assert list(session.scalars(select(LiquidationHeatmap))) == []


def _sqlite_session(include_prices: bool) -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Asset.__table__.create(engine)
    PriceSnapshot.__table__.create(engine)
    SourceHealthCheck.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE liquidations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts DATETIME NOT NULL,
                    asset VARCHAR(10) NOT NULL,
                    longs_liquidated_1h_usd NUMERIC(20, 2),
                    shorts_liquidated_1h_usd NUMERIC(20, 2),
                    longs_liquidated_24h_usd NUMERIC(20, 2),
                    shorts_liquidated_24h_usd NUMERIC(20, 2)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE liquidation_heatmap (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts DATETIME NOT NULL,
                    asset VARCHAR(10) NOT NULL,
                    timeframe VARCHAR(10) NOT NULL,
                    price_low NUMERIC(20, 8) NOT NULL,
                    price_high NUMERIC(20, 8) NOT NULL,
                    liquidation_volume_usd NUMERIC(20, 2) NOT NULL
                )
                """
            )
        )
    session = Session(engine)
    session.add_all(
        [
            Asset(symbol="BTC", name="Bitcoin", enabled=True),
            Asset(symbol="ETH", name="Ethereum", enabled=True),
            Asset(symbol="SOL", name="Solana", enabled=True),
        ]
    )
    if include_prices:
        session.add_all(
            [
                _price_snapshot("BTC", Decimal("100000")),
                _price_snapshot("ETH", Decimal("3000")),
            ]
        )
    session.commit()
    return session


def _price_snapshot(asset: str, price: Decimal) -> PriceSnapshot:
    return PriceSnapshot(
        source="binance",
        symbol=asset,
        quote_currency="USDT",
        price=price,
        collected_at=datetime(2026, 5, 16, 12, 17, tzinfo=timezone.utc),
        raw_payload={"symbol": f"{asset}USDT"},
    )
