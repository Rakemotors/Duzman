"""RSI indicator calculation for OHLCV candles."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd
import pandas_ta as ta

from duzman.collectors import OHLCVRecord
from duzman.indicators.common import quantize_indicator_value


def compute_rsi(candles: list[OHLCVRecord], period: int = 14) -> Decimal | None:
    """Return the latest RSI value for closing prices, or None when unavailable."""
    if len(candles) <= period:
        return None

    close_series = pd.Series([float(candle.close) for candle in candles])
    rsi_series = ta.rsi(close_series, length=period)
    if rsi_series is None:
        return None

    latest_value = rsi_series.dropna().iloc[-1:]  # Keep pandas from raising on all-NaN results.
    if latest_value.empty:
        return None
    return quantize_indicator_value(Decimal(str(latest_value.iloc[0])))
