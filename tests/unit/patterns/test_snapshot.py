"""Tests for Pattern Engine metrics snapshot building."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import (
    Asset,
    EtfFlow,
    FundingRate,
    GlobalMetric,
    Indicator,
    Liquidation,
    OpenInterest,
    PriceSnapshot,
)
from duzman.patterns.known_metrics import KNOWN_METRICS
from duzman.patterns.snapshot import build_snapshot

NOW = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create an in-memory async SQLite session with snapshot source tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for statement in _schema_statements():
            await connection.exec_driver_sql(statement)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all(
            [Asset(symbol=symbol, name=symbol) for symbol in ["BTC", "ETH", "SOL"]]
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_empty_db_returns_all_none(session: AsyncSession) -> None:
    """Empty metric tables should produce a complete all-None snapshot."""
    snapshot = await build_snapshot(session, ["BTC", "SOL"], NOW)

    assert set(snapshot.assets) == {"BTC", "SOL"}
    assert set(snapshot.global_metrics) == {
        "fear_greed_index",
        "btc_dominance",
        "btc_dominance_change_7d_pct",
    }
    assert set(snapshot.assets["BTC"].values) == KNOWN_METRICS - set(snapshot.global_metrics)
    assert all(value is None for value in snapshot.global_metrics.values())
    assert all(
        value is None
        for asset_metrics in snapshot.assets.values()
        for value in asset_metrics.values.values()
    )


@pytest.mark.asyncio
async def test_rsi_read_per_timeframe(session: AsyncSession) -> None:
    """RSI rows should map to per-timeframe metric names."""
    await _add_indicators(
        session,
        [
            _indicator("BTC", "RSI", "1h", "11"),
            _indicator("BTC", "RSI", "4h", "44"),
            _indicator("BTC", "RSI", "1d", "70"),
            _indicator("BTC", "RSI", "1w", "80"),
        ],
    )

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["RSI_1h"] == 11.0
    assert values["RSI_4h"] == 44.0
    assert values["RSI_1d"] == 70.0
    assert values["RSI_1w"] == 80.0


@pytest.mark.asyncio
async def test_stoch_read(session: AsyncSession) -> None:
    """Stochastic K/D rows should map to 1h and 4h metrics."""
    await _add_indicators(
        session,
        [
            _indicator("BTC", "STOCH_K", "1h", "10"),
            _indicator("BTC", "STOCH_K", "4h", "20"),
            _indicator("BTC", "STOCH_D", "1h", "30"),
            _indicator("BTC", "STOCH_D", "4h", "40"),
        ],
    )

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["stoch_k_1h"] == 10.0
    assert values["stoch_k_4h"] == 20.0
    assert values["stoch_d_1h"] == 30.0
    assert values["stoch_d_4h"] == 40.0


@pytest.mark.asyncio
async def test_volatility_read(session: AsyncSession) -> None:
    """Realized volatility should be read from indicators."""
    await _add_indicators(session, [_indicator("BTC", "VOLATILITY_24H", None, "123.45")])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["volatility_24h_annualized"] == 123.45


@pytest.mark.asyncio
async def test_premium_discount_averaged_across_exchanges(session: AsyncSession) -> None:
    """Premium/discount rows in the freshness window should be averaged."""
    await _add_indicators(
        session,
        [
            _indicator("BTC", "PREMIUM_DISCOUNT", None, "1.0"),
            _indicator("BTC", "PREMIUM_DISCOUNT", None, "3.0"),
        ],
    )

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["premium_discount_pct"] == 2.0


@pytest.mark.asyncio
async def test_price_changes_read(session: AsyncSession) -> None:
    """Price change metrics should read 24h directly and 7d from price history."""
    await _add_prices(
        session,
        [
            _price("BTC", NOW - timedelta(days=7), "100", "1"),
            _price("BTC", NOW - timedelta(minutes=5), "125", "5"),
        ],
    )

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["price_change_24h_pct"] == 5.0
    assert values["price_change_7d_pct"] == 25.0


@pytest.mark.asyncio
async def test_liquidations_read(session: AsyncSession) -> None:
    """Liquidations should read latest 24h long and short values."""
    session.add(
        Liquidation(
            id=1,
            ts=NOW - timedelta(minutes=1),
            asset="BTC",
            longs_liquidated_1h_usd=Decimal("1"),
            shorts_liquidated_1h_usd=Decimal("2"),
            longs_liquidated_24h_usd=Decimal("1000000"),
            shorts_liquidated_24h_usd=Decimal("2000000"),
        )
    )
    await session.commit()

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["liquidations_longs_24h_usd"] == 1_000_000.0
    assert values["liquidations_shorts_24h_usd"] == 2_000_000.0


@pytest.mark.asyncio
async def test_fear_greed_in_global(session: AsyncSession) -> None:
    """Fear and Greed should be a global metric only."""
    session.add(_global(1, "fear_greed_index", "64", NOW))
    await session.commit()

    snapshot = await build_snapshot(session, ["BTC"], NOW)

    assert snapshot.global_metrics["fear_greed_index"] == 64.0
    assert "fear_greed_index" not in snapshot.assets["BTC"].values


@pytest.mark.asyncio
async def test_btc_dominance_in_global(session: AsyncSession) -> None:
    """BTC dominance should be a global metric only."""
    session.add(_global(1, "btc_dominance", "55.5", NOW))
    await session.commit()

    snapshot = await build_snapshot(session, ["BTC"], NOW)

    assert snapshot.global_metrics["btc_dominance"] == 55.5
    assert "btc_dominance" not in snapshot.assets["BTC"].values


@pytest.mark.asyncio
async def test_funding_rate_avg_three_exchanges(session: AsyncSession) -> None:
    """Funding average should use values from at least two exchanges."""
    await _add_funding(session, ["0.01", "0.02", "0.03"])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["funding_rate_avg"] == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_funding_rate_avg_single_exchange_returns_none(session: AsyncSession) -> None:
    """A single funding exchange should not produce an average."""
    await _add_funding(session, ["0.01"])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["funding_rate_avg"] is None


@pytest.mark.asyncio
async def test_funding_dislocation_pct(session: AsyncSession) -> None:
    """Funding dislocation should be max minus min in the last hour."""
    await _add_funding(session, ["0.01", "0.04", "-0.01"])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["funding_dislocation_pct"] == pytest.approx(0.05)


@pytest.mark.asyncio
async def test_oi_change_24h_pct(session: AsyncSession) -> None:
    """Open interest change should compare summed latest exchange rows."""
    session.add_all(
        [
            _open_interest(1, "BTC", "binance", "100", NOW - timedelta(hours=24)),
            _open_interest(2, "BTC", "okx", "100", NOW - timedelta(hours=24)),
            _open_interest(3, "BTC", "binance", "150", NOW - timedelta(minutes=10)),
            _open_interest(4, "BTC", "okx", "150", NOW - timedelta(minutes=10)),
        ]
    )
    await session.commit()

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["oi_change_24h_pct"] == 50.0


@pytest.mark.asyncio
async def test_oi_change_returns_none_when_no_history(session: AsyncSession) -> None:
    """Missing 24h OI history should produce None."""
    session.add(_open_interest(1, "BTC", "binance", "150", NOW - timedelta(minutes=10)))
    await session.commit()

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["oi_change_24h_pct"] is None


@pytest.mark.asyncio
async def test_etf_streak_positive(session: AsyncSession) -> None:
    """Positive ETF flow streak should be returned as a positive count."""
    await _add_etf_flows(session, "BTC", ["1", "2", "3", "4", "5", "-1"])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["etf_net_flow_streak_days"] == 5.0


@pytest.mark.asyncio
async def test_etf_streak_negative(session: AsyncSession) -> None:
    """Negative ETF flow streak should be returned as a negative count."""
    await _add_etf_flows(session, "BTC", ["-1", "-2", "-3", "4"])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["etf_net_flow_streak_days"] == -3.0


@pytest.mark.asyncio
async def test_etf_cum_flow_5d_converted_to_usd(session: AsyncSession) -> None:
    """ETF cumulative flow should convert stored millions to USD."""
    await _add_etf_flows(session, "BTC", ["100"])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["etf_cum_flow_5d_usd"] == 100_000_000.0


@pytest.mark.asyncio
async def test_price_vs_btc_for_btc_is_none(session: AsyncSession) -> None:
    """BTC should not have a price-vs-BTC relative change metric."""
    await _add_prices(session, [_price("BTC", NOW, "100", "1")])

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["price_vs_btc_change_7d_pct"] is None


@pytest.mark.asyncio
async def test_price_vs_btc_change_computation(session: AsyncSession) -> None:
    """Relative seven-day price change should compare asset/BTC ratios."""
    await _add_prices(
        session,
        [
            _price("BTC", NOW - timedelta(days=7), "100", "1"),
            _price("BTC", NOW, "200", "1"),
            _price("SOL", NOW - timedelta(days=7), "10", "1"),
            _price("SOL", NOW, "15", "1"),
        ],
    )

    values = (await build_snapshot(session, ["SOL"], NOW)).assets["SOL"].values

    assert values["price_vs_btc_change_7d_pct"] == pytest.approx(-25.0)


@pytest.mark.asyncio
async def test_btc_dominance_change_7d_pct(session: AsyncSession) -> None:
    """BTC dominance change should be current minus closest seven-day value."""
    session.add_all(
        [
            _global(1, "btc_dominance", "52.0", NOW - timedelta(days=7)),
            _global(2, "btc_dominance", "55.5", NOW),
        ]
    )
    await session.commit()

    snapshot = await build_snapshot(session, ["BTC"], NOW)

    assert snapshot.global_metrics["btc_dominance_change_7d_pct"] == 3.5


@pytest.mark.asyncio
async def test_stale_metric_returns_none(session: AsyncSession) -> None:
    """Rows older than the staleness window should not populate direct metrics."""
    await _add_indicators(
        session,
        [_indicator("BTC", "RSI", "1h", "70", ts=NOW - timedelta(hours=3))],
    )

    values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["RSI_1h"] is None


@pytest.mark.asyncio
async def test_one_failed_derived_does_not_break_snapshot(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A failed derived metric should log and leave that metric as None."""
    import duzman.patterns.snapshot as snapshot_module

    await _add_funding(session, ["0.01", "0.03"])

    async def fail_oi(session: AsyncSession, asset: str, now: datetime) -> float | None:
        """Raise a controlled derived metric failure."""
        raise RuntimeError("broken calculation")

    monkeypatch.setattr(snapshot_module, "_compute_oi_change_24h_pct", fail_oi)

    with caplog.at_level(logging.WARNING):
        values = (await build_snapshot(session, ["BTC"], NOW)).assets["BTC"].values

    assert values["oi_change_24h_pct"] is None
    assert values["funding_rate_avg"] == pytest.approx(0.02)
    assert "derived_metric_failed" in caplog.text
    assert "metric_name=oi_change_24h_pct" in caplog.text


def _schema_statements() -> list[str]:
    """Return SQLite DDL for tables used by snapshot tests."""
    return [
        """
        CREATE TABLE assets (
            symbol VARCHAR(10) PRIMARY KEY,
            name VARCHAR(50),
            enabled BOOLEAN,
            added_at DATETIME
        )
        """,
        """
        CREATE TABLE indicators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL,
            asset VARCHAR(10) NOT NULL,
            indicator_type VARCHAR(20) NOT NULL,
            timeframe VARCHAR(10),
            value NUMERIC(12, 4),
            parameters JSON
        )
        """,
        """
        CREATE TABLE price_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source VARCHAR(20) NOT NULL,
            asset VARCHAR(10) NOT NULL,
            quote_currency VARCHAR(10) NOT NULL,
            price_usd NUMERIC(20, 8) NOT NULL,
            ts DATETIME NOT NULL,
            created_at DATETIME,
            raw_payload JSON,
            volume_24h_quote NUMERIC(20, 2),
            price_change_24h_pct NUMERIC(8, 4)
        )
        """,
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
        """,
        """
        CREATE TABLE global_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL,
            metric_name VARCHAR(30) NOT NULL,
            value NUMERIC(12, 4)
        )
        """,
        """
        CREATE TABLE funding_rates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL,
            asset VARCHAR(10) NOT NULL,
            exchange VARCHAR(20) NOT NULL,
            funding_rate_pct NUMERIC(10, 6),
            next_funding_time DATETIME,
            predicted_rate NUMERIC(10, 6)
        )
        """,
        """
        CREATE TABLE open_interest (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL,
            asset VARCHAR(10) NOT NULL,
            exchange VARCHAR(20) NOT NULL,
            oi_usd NUMERIC(20, 2),
            oi_contracts NUMERIC(20, 2)
        )
        """,
        """
        CREATE TABLE etf_flows (
            date DATE NOT NULL,
            asset VARCHAR(10) NOT NULL,
            provider VARCHAR(20) NOT NULL,
            flow_usd_m NUMERIC(10, 2),
            PRIMARY KEY (date, asset, provider)
        )
        """,
    ]


def _indicator(
    asset: str,
    indicator_type: str,
    timeframe: str | None,
    value: str,
    ts: datetime = NOW,
) -> Indicator:
    """Build an indicator ORM row."""
    return Indicator(
        ts=ts,
        asset=asset,
        indicator_type=indicator_type,
        timeframe=timeframe,
        value=Decimal(value),
        parameters={},
    )


async def _add_indicators(session: AsyncSession, rows: list[Indicator]) -> None:
    """Persist indicator rows with deterministic SQLite ids."""
    for index, row in enumerate(rows, start=1):
        row.id = index
    session.add_all(rows)
    await session.commit()


def _price(asset: str, ts: datetime, price: str, change_24h: str) -> PriceSnapshot:
    """Build a price snapshot ORM row."""
    return PriceSnapshot(
        source="binance",
        asset=asset,
        quote_currency="USD",
        price_usd=Decimal(price),
        ts=ts,
        created_at=ts,
        raw_payload={},
        volume_24h_quote=Decimal("1"),
        price_change_24h_pct=Decimal(change_24h),
    )


async def _add_prices(session: AsyncSession, rows: list[PriceSnapshot]) -> None:
    """Persist price rows with deterministic SQLite ids."""
    for index, row in enumerate(rows, start=1):
        row.id = index
    session.add_all(rows)
    await session.commit()


def _global(row_id: int, metric_name: str, value: str, ts: datetime) -> GlobalMetric:
    """Build a global metric ORM row."""
    return GlobalMetric(id=row_id, ts=ts, metric_name=metric_name, value=Decimal(value))


async def _add_funding(session: AsyncSession, values: list[str]) -> None:
    """Persist funding rows for BTC using distinct exchange names."""
    exchanges = ["binance", "bybit", "okx"]
    session.add_all(
        [
            FundingRate(
                id=index,
                ts=NOW - timedelta(minutes=10),
                asset="BTC",
                exchange=exchanges[index - 1],
                funding_rate_pct=Decimal(value),
                next_funding_time=None,
                predicted_rate=None,
            )
            for index, value in enumerate(values, start=1)
        ]
    )
    await session.commit()


def _open_interest(
    row_id: int,
    asset: str,
    exchange: str,
    oi_usd: str,
    ts: datetime,
) -> OpenInterest:
    """Build an open interest ORM row."""
    return OpenInterest(
        id=row_id,
        ts=ts,
        asset=asset,
        exchange=exchange,
        oi_usd=Decimal(oi_usd),
        oi_contracts=Decimal("1"),
    )


async def _add_etf_flows(session: AsyncSession, asset: str, values: list[str]) -> None:
    """Persist daily ETF flow rows newest first."""
    today = date(2026, 5, 17)
    session.add_all(
        [
            EtfFlow(
                date=today - timedelta(days=index),
                asset=asset,
                provider="farside",
                flow_usd_m=Decimal(value),
            )
            for index, value in enumerate(values)
        ]
    )
    await session.commit()
