"""Shared normalized collector records for Stage A market metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
