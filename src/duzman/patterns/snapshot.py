"""Build immutable Pattern Engine metric snapshots from database rows."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.repositories import SnapshotReadRepository
from duzman.logging_config import get_logger, log_event, safe_error_message
from duzman.patterns.known_metrics import KNOWN_METRICS

GLOBAL_METRICS = frozenset(
    {"fear_greed_index", "btc_dominance", "btc_dominance_change_7d_pct"}
)
ASSET_METRICS = tuple(sorted(KNOWN_METRICS - GLOBAL_METRICS))
LOGGER = get_logger(__name__)


class AssetMetrics(BaseModel):
    """Metric values for one asset."""

    asset: str
    values: dict[str, float | None]
    model_config = ConfigDict(extra="forbid", frozen=True)


class MetricsSnapshot(BaseModel):
    """Immutable metric snapshot for Pattern Engine evaluation."""

    built_at: datetime
    assets: dict[str, AssetMetrics]
    global_metrics: dict[str, float | None]
    model_config = ConfigDict(extra="forbid", frozen=True)


async def build_snapshot(
    session: AsyncSession,
    assets: list[str],
    now: datetime,
    max_staleness_minutes: int = 90,
) -> MetricsSnapshot:
    """Build a per-asset metric snapshot from database state."""
    now = _require_aware_utc(now)
    repository = SnapshotReadRepository(session)
    since = now - timedelta(minutes=max_staleness_minutes)
    values_by_asset = {asset: dict.fromkeys(ASSET_METRICS) for asset in assets}

    await _load_direct_indicators(repository, values_by_asset, assets, since, now)
    await _load_direct_prices(repository, values_by_asset, assets, since, now)
    await _load_direct_liquidations(repository, values_by_asset, assets, since, now)

    global_metrics: dict[str, float | None] = {
        "fear_greed_index": _to_float_or_none(
            await _latest_global_value(repository, "fear_greed_index", since, now)
        ),
        "btc_dominance": _to_float_or_none(
            await _latest_global_value(repository, "btc_dominance", since, now)
        ),
        "btc_dominance_change_7d_pct": await _safe_derived_global(
            "btc_dominance_change_7d_pct",
            _compute_btc_dominance_change_7d_pct(session, now),
        ),
    }

    for asset in assets:
        asset_values = values_by_asset[asset]
        derived_specs: tuple[tuple[str, Awaitable[float | int | None]], ...] = (
            ("funding_rate_avg", _compute_funding_rate_avg(session, asset, now)),
            (
                "funding_dislocation_pct",
                _compute_funding_dislocation_pct(session, asset, now),
            ),
            ("oi_change_24h_pct", _compute_oi_change_24h_pct(session, asset, now)),
            (
                "etf_net_flow_streak_days",
                _compute_etf_net_flow_streak_days(session, asset, now),
            ),
            ("etf_cum_flow_5d_usd", _compute_etf_cum_flow_5d_usd(session, asset, now)),
            (
                "price_vs_btc_change_7d_pct",
                _compute_price_vs_btc_change_7d_pct(session, asset, now),
            ),
        )
        for metric_name, awaitable in derived_specs:
            asset_values[metric_name] = await _safe_derived_asset(
                metric_name,
                asset,
                awaitable,
            )

    snapshot = MetricsSnapshot(
        built_at=now,
        assets={
            asset: AssetMetrics(asset=asset, values=values)
            for asset, values in values_by_asset.items()
        },
        global_metrics=global_metrics,
    )
    log_event(
        LOGGER,
        "snapshot_built",
        count_assets=len(assets),
        count_non_null_metrics=_count_non_null_metrics(snapshot),
    )
    return snapshot


async def _load_direct_indicators(
    repository: SnapshotReadRepository,
    values_by_asset: dict[str, dict[str, float | None]],
    assets: list[str],
    since: datetime,
    now: datetime,
) -> None:
    """Load direct indicator metrics into the snapshot value mapping."""
    indicator_mapping = {
        ("RSI", "1h"): "RSI_1h",
        ("RSI", "4h"): "RSI_4h",
        ("RSI", "1d"): "RSI_1d",
        ("RSI", "1w"): "RSI_1w",
        ("STOCH_K", "1h"): "stoch_k_1h",
        ("STOCH_K", "4h"): "stoch_k_4h",
        ("STOCH_D", "1h"): "stoch_d_1h",
        ("STOCH_D", "4h"): "stoch_d_4h",
        ("VOLATILITY_24H", None): "volatility_24h_annualized",
    }
    seen: set[tuple[str, str]] = set()
    for row in await repository.latest_indicators(assets, since, now):
        metric_name = indicator_mapping.get((row.indicator_type, row.timeframe))
        if metric_name is None:
            metric_name = indicator_mapping.get((row.indicator_type, None))
        if metric_name is None:
            continue
        key = (row.asset, metric_name)
        if key in seen:
            continue
        values_by_asset[row.asset][metric_name] = _to_float_or_none(row.value)
        seen.add(key)

    for asset in assets:
        premium = await repository.average_indicator_value(
            asset,
            "PREMIUM_DISCOUNT",
            since,
            now,
        )
        values_by_asset[asset]["premium_discount_pct"] = _to_float_or_none(premium)


async def _load_direct_prices(
    repository: SnapshotReadRepository,
    values_by_asset: dict[str, dict[str, float | None]],
    assets: list[str],
    since: datetime,
    now: datetime,
) -> None:
    """Load direct price-change metrics into the snapshot value mapping."""
    for asset in assets:
        latest = await repository.latest_price_snapshot(asset, since, now)
        if latest is None:
            continue
        values_by_asset[asset]["price_change_24h_pct"] = _to_float_or_none(
            latest.price_change_24h_pct
        )
        values_by_asset[asset]["price_change_7d_pct"] = await _price_change_pct(
            repository,
            asset,
            now,
            days=7,
        )


async def _load_direct_liquidations(
    repository: SnapshotReadRepository,
    values_by_asset: dict[str, dict[str, float | None]],
    assets: list[str],
    since: datetime,
    now: datetime,
) -> None:
    """Load direct liquidation metrics into the snapshot value mapping."""
    for asset in assets:
        latest = await repository.latest_liquidation(asset, since, now)
        if latest is None:
            continue
        values_by_asset[asset]["liquidations_longs_24h_usd"] = _to_float_or_none(
            latest.longs_liquidated_24h_usd
        )
        values_by_asset[asset]["liquidations_shorts_24h_usd"] = _to_float_or_none(
            latest.shorts_liquidated_24h_usd
        )


async def _compute_funding_rate_avg(
    session: AsyncSession,
    asset: str,
    now: datetime,
) -> float | None:
    """Compute average funding rate across at least two exchanges in the last hour."""
    rows = await SnapshotReadRepository(session).funding_rates(
        asset,
        now - timedelta(hours=1),
        now,
    )
    exchanges = {row.exchange for row in rows}
    if len(exchanges) < 2:
        return None
    values = [_to_float_or_none(row.funding_rate_pct) for row in rows]
    numeric_values = [value for value in values if value is not None]
    if len(numeric_values) < 2:
        return None
    return sum(numeric_values) / len(numeric_values)


async def _compute_funding_dislocation_pct(
    session: AsyncSession,
    asset: str,
    now: datetime,
) -> float | None:
    """Compute max-minus-min funding-rate dislocation across exchanges."""
    rows = await SnapshotReadRepository(session).funding_rates(
        asset,
        now - timedelta(hours=1),
        now,
    )
    exchanges = {row.exchange for row in rows}
    if len(exchanges) < 2:
        return None
    values = [_to_float_or_none(row.funding_rate_pct) for row in rows]
    numeric_values = [value for value in values if value is not None]
    if len(numeric_values) < 2:
        return None
    return max(numeric_values) - min(numeric_values)


async def _compute_oi_change_24h_pct(
    session: AsyncSession,
    asset: str,
    now: datetime,
) -> float | None:
    """Compute percentage change in summed open interest over 24 hours."""
    repository = SnapshotReadRepository(session)
    oi_now = await repository.open_interest_sum(asset, now - timedelta(hours=1), now)
    oi_24h_ago = await repository.open_interest_sum(
        asset,
        now - timedelta(hours=25),
        now - timedelta(hours=23),
    )
    if oi_now is None or oi_24h_ago is None or oi_24h_ago == 0:
        return None
    return (float(oi_now) - float(oi_24h_ago)) / float(oi_24h_ago) * 100


async def _compute_etf_net_flow_streak_days(
    session: AsyncSession,
    asset: str,
    now: datetime,
) -> int | None:
    """Compute signed ETF net-flow streak length from recent daily rows."""
    del now
    rows = await SnapshotReadRepository(session).recent_etf_flows(asset)
    if not rows or rows[0].flow_usd_m in (None, 0):
        return None
    first = float(rows[0].flow_usd_m)
    sign = 1 if first > 0 else -1
    streak = 0
    for row in rows:
        value = _to_float_or_none(row.flow_usd_m)
        if value is None or value == 0 or (value > 0) != (sign > 0):
            break
        streak += 1
    return sign * streak if streak else None


async def _compute_etf_cum_flow_5d_usd(
    session: AsyncSession,
    asset: str,
    now: datetime,
) -> float | None:
    """Compute cumulative five-day ETF flow in USD."""
    flow_usd_m = await SnapshotReadRepository(session).etf_flow_sum_since(
        asset,
        now.date() - timedelta(days=5),
    )
    if flow_usd_m is None:
        return None
    return float(flow_usd_m) * 1_000_000


async def _compute_price_vs_btc_change_7d_pct(
    session: AsyncSession,
    asset: str,
    now: datetime,
) -> float | None:
    """Compute seven-day price ratio change versus BTC."""
    if asset == "BTC":
        return None
    repository = SnapshotReadRepository(session)
    price_now = await repository.latest_price_snapshot(asset, until=now)
    price_7d = await repository.closest_price_snapshot(asset, now - timedelta(days=7))
    btc_now = await repository.latest_price_snapshot("BTC", until=now)
    btc_7d = await repository.closest_price_snapshot("BTC", now - timedelta(days=7))
    if price_now is None or price_7d is None or btc_now is None or btc_7d is None:
        return None
    if btc_now.price == 0 or btc_7d.price == 0:
        return None
    ratio_now = float(price_now.price) / float(btc_now.price)
    ratio_7d = float(price_7d.price) / float(btc_7d.price)
    if ratio_7d == 0:
        return None
    return (ratio_now / ratio_7d - 1) * 100


async def _compute_btc_dominance_change_7d_pct(
    session: AsyncSession,
    now: datetime,
) -> float | None:
    """Compute absolute seven-day BTC dominance change in percentage points."""
    repository = SnapshotReadRepository(session)
    current = await repository.latest_global_metric("btc_dominance", until=now)
    previous = await repository.closest_global_metric(
        "btc_dominance",
        now - timedelta(days=7),
    )
    if current is None or previous is None:
        return None
    current_value = _to_float_or_none(current.value)
    previous_value = _to_float_or_none(previous.value)
    if current_value is None or previous_value is None:
        return None
    return current_value - previous_value


async def _latest_global_value(
    repository: SnapshotReadRepository,
    metric_name: str,
    since: datetime,
    now: datetime,
) -> Decimal | None:
    """Return a fresh global metric value."""
    row = await repository.latest_global_metric(metric_name, since, now)
    return None if row is None else row.value


async def _price_change_pct(
    repository: SnapshotReadRepository,
    asset: str,
    now: datetime,
    days: int,
) -> float | None:
    """Compute price percentage change from the closest historical snapshot."""
    latest = await repository.latest_price_snapshot(asset, until=now)
    previous = await repository.closest_price_snapshot(asset, now - timedelta(days=days))
    if latest is None or previous is None or previous.price == 0:
        return None
    return (float(latest.price) - float(previous.price)) / float(previous.price) * 100


async def _safe_derived_asset(
    metric_name: str,
    asset: str,
    awaitable: Awaitable[float | int | None],
) -> float | None:
    """Return a derived metric value or None when calculation fails."""
    try:
        return _to_float_or_none(await awaitable)
    except Exception as exc:  # noqa: BLE001 - per-metric degradation is required.
        log_event(
            LOGGER,
            "derived_metric_failed",
            level=logging.WARNING,
            metric_name=metric_name,
            asset=asset,
            error=safe_error_message(exc),
        )
        return None


async def _safe_derived_global(
    metric_name: str,
    awaitable: Awaitable[float | int | None],
) -> float | None:
    """Return a derived global metric value or None when calculation fails."""
    try:
        return _to_float_or_none(await awaitable)
    except Exception as exc:  # noqa: BLE001 - per-metric degradation is required.
        log_event(
            LOGGER,
            "derived_metric_failed",
            level=logging.WARNING,
            metric_name=metric_name,
            asset=None,
            error=safe_error_message(exc),
        )
        return None


def _to_float_or_none(value: Decimal | float | int | None) -> float | None:
    """Convert numeric database values to float while preserving None."""
    if value is None:
        return None
    return float(value)


def _count_non_null_metrics(snapshot: MetricsSnapshot) -> int:
    """Count populated metric values in a snapshot."""
    return sum(value is not None for value in snapshot.global_metrics.values()) + sum(
        value is not None
        for asset_metrics in snapshot.assets.values()
        for value in asset_metrics.values.values()
    )


def _require_aware_utc(value: datetime) -> datetime:
    """Validate and normalize an aware UTC datetime."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must be timezone-aware UTC datetime")
    return value.astimezone(timezone.utc)
