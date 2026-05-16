"""Shared normalized collector records for Stage A market metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class FundingRateRecord:
    """Normalized funding-rate row matching the database model fields."""

    ts: datetime
    asset: str
    exchange: str
    funding_rate_pct: Decimal
    next_funding_time: datetime | None
    predicted_rate: Decimal | None = None


@dataclass(frozen=True)
class OpenInterestRecord:
    """Normalized open-interest row matching the database model fields."""

    ts: datetime
    asset: str
    exchange: str
    oi_usd: Decimal
    oi_contracts: Decimal


@dataclass(frozen=True)
class LongShortRatioRecord:
    """Normalized long/short ratio row matching the database model fields."""

    ts: datetime
    asset: str
    exchange: str
    ratio_type: str
    long_pct: float
    short_pct: float
    ratio: float


@dataclass(frozen=True)
class OHLCVRecord:
    """Normalized OHLCV candle row for future indicator calculations."""

    ts: datetime
    asset: str
    exchange: str
    interval: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    quote_volume: Decimal


@dataclass(frozen=True)
class ETFFlowRecord:
    """Normalized ETF flow row matching the etf_flows table primary key."""

    date: date
    asset: str
    provider: str
    flow_usd_m: Decimal


@dataclass(frozen=True)
class LiquidationRecord:
    """Normalized liquidation row matching the liquidations table fields."""

    ts: datetime
    asset: str
    longs_1h_usd: Decimal
    shorts_1h_usd: Decimal
    longs_24h_usd: Decimal
    shorts_24h_usd: Decimal


@dataclass(frozen=True)
class HeatmapBucketRecord:
    """Normalized liquidation heatmap bucket for persisted read-only views."""

    ts: datetime
    asset: str
    timeframe: str
    price_low: Decimal
    price_high: Decimal
    liquidation_volume_usd: Decimal


@dataclass(frozen=True)
class GlobalMetricRecord:
    """Normalized global metric row matching the global_metrics table fields."""

    ts: datetime
    metric_name: str
    value: Decimal
