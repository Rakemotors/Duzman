"""Scheduled deterministic indicator collection job."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger

from duzman.assets import STAGE_A_ASSETS
from duzman.collectors import (
    BinanceCollector,
    BybitCollector,
    MarketDataSnapshot,
    OHLCVRecord,
)
from duzman.indicators import (
    IndicatorRecord,
    compute_premium_discount,
    compute_realized_volatility_24h,
    compute_rsi,
    compute_stochastic,
)
from duzman.logging_config import get_logger, log_event, safe_error_message
from duzman.repositories import IndicatorRepository

HOURLY_INDICATOR_COLLECTION_JOB_ID = "hourly_indicator_collection"
STAGE_A_INDICATOR_ASSETS = STAGE_A_ASSETS


async def collect_indicators_job(
    session_factory: Callable[[], Any],
    binance_collector: BinanceCollector,
    bybit_collector: BybitCollector,
    repository: IndicatorRepository,
    assets: Sequence[str] = STAGE_A_INDICATOR_ASSETS,
) -> int:
    """Collect deterministic indicators for Stage A assets and persist them."""
    logger = get_logger(__name__)
    log_event(logger, "indicator_collection_started", asset_count=len(assets))
    session = session_factory()
    records: list[IndicatorRecord] = []
    try:
        for asset in assets:
            try:
                records.extend(
                    await _collect_asset_indicators(
                        asset,
                        binance_collector,
                        bybit_collector,
                    )
                )
            except Exception as exc:
                log_event(
                    logger,
                    "indicator_asset_collection_failed",
                    level=logging.ERROR,
                    asset=asset,
                    safe_error_message=safe_error_message(exc),
                )

        inserted_count = await repository.save_indicators(session, records)
        commit_result = session.commit()
        if inspect.isawaitable(commit_result):
            await commit_result
    finally:
        close_result = session.close()
        if inspect.isawaitable(close_result):
            await close_result

    log_event(
        logger,
        "indicator_collection_completed",
        asset_count=len(assets),
        record_count=len(records),
        inserted_count=inserted_count,
    )
    return inserted_count


def register_hourly_indicator_collection_job(
    scheduler: BaseScheduler,
    indicator_callable: Callable[[], Any],
) -> None:
    """Register the hourly indicator collection job without starting a scheduler."""
    scheduler.add_job(
        indicator_callable,
        trigger=CronTrigger(minute=23, timezone=UTC),
        id=HOURLY_INDICATOR_COLLECTION_JOB_ID,
        replace_existing=True,
    )


async def _collect_asset_indicators(
    asset: str,
    binance_collector: BinanceCollector,
    bybit_collector: BybitCollector,
) -> list[IndicatorRecord]:
    collected_at = datetime.now(UTC)
    records: list[IndicatorRecord] = []

    candles_1h = await binance_collector.fetch_ohlcv(asset, "1h", limit=100)
    records.extend(
        _indicator_records_from_ohlcv(
            asset,
            "1h",
            candles_1h,
            collected_at,
            include_volatility=True,
        )
    )

    candles_4h = await binance_collector.fetch_ohlcv(asset, "4h", limit=100)
    records.extend(_indicator_records_from_ohlcv(asset, "4h", candles_4h, collected_at))

    candles_1d = await binance_collector.fetch_ohlcv(asset, "1d", limit=100)
    records.extend(_rsi_record(asset, "1d", candles_1d, collected_at))

    candles_1w = await binance_collector.fetch_ohlcv(asset, "1w", limit=100)
    records.extend(_rsi_record(asset, "1w", candles_1w, collected_at))

    records.extend(
        await _premium_discount_records(
            asset,
            binance_collector,
            bybit_collector,
            collected_at,
        )
    )
    return records


def _indicator_records_from_ohlcv(
    asset: str,
    timeframe: str,
    candles: list[OHLCVRecord],
    collected_at: datetime,
    include_volatility: bool = False,
) -> list[IndicatorRecord]:
    records = _rsi_record(asset, timeframe, candles, collected_at)
    stochastic = compute_stochastic(candles)
    if stochastic is not None:
        stochastic_k, stochastic_d = stochastic
        records.extend(
            [
                IndicatorRecord(
                    ts=collected_at,
                    asset=asset,
                    indicator_type="stochastic_k",
                    timeframe=timeframe,
                    value=stochastic_k,
                    parameters={"k_period": 14, "d_period": 3, "smoothing": 3},
                ),
                IndicatorRecord(
                    ts=collected_at,
                    asset=asset,
                    indicator_type="stochastic_d",
                    timeframe=timeframe,
                    value=stochastic_d,
                    parameters={"k_period": 14, "d_period": 3, "smoothing": 3},
                ),
            ]
        )
    if include_volatility:
        volatility = compute_realized_volatility_24h(candles)
        if volatility is not None:
            records.append(
                IndicatorRecord(
                    ts=collected_at,
                    asset=asset,
                    indicator_type="volatility_24h",
                    timeframe=timeframe,
                    value=volatility,
                    parameters={"window_hours": 24, "annualized": True},
                )
            )
    return records


def _rsi_record(
    asset: str,
    timeframe: str,
    candles: list[OHLCVRecord],
    collected_at: datetime,
) -> list[IndicatorRecord]:
    rsi_value = compute_rsi(candles)
    if rsi_value is None:
        return []
    return [
        IndicatorRecord(
            ts=collected_at,
            asset=asset,
            indicator_type="rsi",
            timeframe=timeframe,
            value=rsi_value,
            parameters={"period": 14},
        )
    ]


async def _premium_discount_records(
    asset: str,
    binance_collector: BinanceCollector,
    bybit_collector: BybitCollector,
    collected_at: datetime,
) -> list[IndicatorRecord]:
    spot_snapshots = await binance_collector.fetch_tickers([asset])
    mark_prices = await bybit_collector.fetch_mark_prices([asset])
    if not spot_snapshots or not mark_prices:
        return []

    spot_price = _spot_price_for_asset(asset, spot_snapshots)
    mark_price = _mark_price_for_asset(asset, mark_prices)
    if spot_price is None or mark_price is None:
        return []
    return [
        IndicatorRecord(
            ts=collected_at,
            asset=asset,
            indicator_type="premium_discount",
            timeframe="spot",
            value=compute_premium_discount(mark_price, spot_price),
            parameters={"perp_source": "bybit", "spot_source": "binance"},
        )
    ]


def _spot_price_for_asset(
    asset: str,
    spot_snapshots: Sequence[MarketDataSnapshot],
    ) -> Decimal | None:
    for snapshot in spot_snapshots:
        if snapshot.asset == asset:
            return snapshot.price_usd
    return None


def _mark_price_for_asset(
    asset: str,
    mark_prices: Sequence[dict[str, Any]],
) -> Decimal | None:
    for record in mark_prices:
        if record.get("asset") == asset and isinstance(record.get("mark_price"), Decimal):
            return record["mark_price"]
    return None
