"""Stochastic oscillator calculation for OHLCV candles."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pandas_ta as ta

from duzman.collectors import OHLCVRecord
from duzman.indicators.common import quantize_indicator_value


def compute_stochastic(
    candles: list[OHLCVRecord],
    k_period: int = 14,
    d_period: int = 3,
    smoothing: int = 3,
) -> tuple[Decimal, Decimal] | None:
    """Return the latest Stochastic %K and %D values, or None when unavailable."""
    if len(candles) < k_period + d_period + smoothing - 2:
        return None

    high_series = pd.Series([float(candle.high) for candle in candles])
    low_series = pd.Series([float(candle.low) for candle in candles])
    close_series = pd.Series([float(candle.close) for candle in candles])
    stochastic_frame = ta.stoch(
        high=high_series,
        low=low_series,
        close=close_series,
        k=k_period,
        d=d_period,
        smooth_k=smoothing,
    )
    if stochastic_frame is None or stochastic_frame.empty:
        return None

    latest_row = stochastic_frame.dropna().iloc[-1:]
    if latest_row.empty:
        return None
    return (
        quantize_indicator_value(Decimal(str(latest_row.iloc[0, 0]))),
        quantize_indicator_value(Decimal(str(latest_row.iloc[0, 1]))),
    )
