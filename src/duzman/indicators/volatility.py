"""Realized volatility calculation for one-hour OHLCV candles."""

from __future__ import annotations

from decimal import Decimal
from math import log, sqrt

from duzman.collectors import OHLCVRecord
from duzman.indicators.common import quantize_indicator_value


MIN_CANDLES_FOR_24H_REALIZED_VOLATILITY = 25
ANNUALIZATION_FACTOR_1H = sqrt(365 * 24)


def compute_realized_volatility_24h(candles_1h: list[OHLCVRecord]) -> Decimal | None:
    """Return annualized 24h realized volatility in percent, or None when unavailable."""
    if len(candles_1h) < MIN_CANDLES_FOR_24H_REALIZED_VOLATILITY:
        return None

    closes = [
        float(candle.close)
        for candle in candles_1h[-MIN_CANDLES_FOR_24H_REALIZED_VOLATILITY:]
    ]
    squared_log_returns = [
        log(current_close / previous_close) ** 2
        for previous_close, current_close in zip(closes, closes[1:])
    ]
    volatility_pct = sqrt(sum(squared_log_returns)) * ANNUALIZATION_FACTOR_1H * 100
    return quantize_indicator_value(Decimal(str(volatility_pct)))
