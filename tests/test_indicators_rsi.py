"""Tests for deterministic RSI indicator calculations."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from duzman.collectors import OHLCVRecord
from duzman.indicators import compute_rsi


def test_compute_rsi_happy_path_has_known_result():
    """RSI should return the expected latest value for stable test candles."""
    assert compute_rsi(_candles(_sample_closes())) == Decimal("82.9717")


def test_compute_rsi_returns_none_when_data_is_insufficient():
    """RSI should return None instead of raising for too few candles."""
    assert compute_rsi(_candles(_sample_closes()[:10])) is None


def test_compute_rsi_uses_period_14_by_default():
    """Default RSI period should be equivalent to passing period=14."""
    candles = _candles(_sample_closes())

    assert compute_rsi(candles) == compute_rsi(candles, period=14)


def test_compute_rsi_supports_custom_period():
    """Custom RSI periods should produce deterministic alternate values."""
    assert compute_rsi(_candles(_sample_closes()), period=5) == Decimal("84.6886")


def _sample_closes() -> list[Decimal]:
    return [
        Decimal(str(value))
        for value in [
            44,
            44.15,
            43.9,
            44.35,
            44.8,
            45.0,
            44.7,
            45.1,
            45.6,
            45.3,
            45.8,
            46.0,
            46.4,
            46.1,
            46.8,
            47.0,
            46.7,
            47.4,
            47.8,
            48.0,
        ]
    ]


def _candles(closes: list[Decimal]) -> list[OHLCVRecord]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        OHLCVRecord(
            ts=base_time + timedelta(hours=index),
            asset="BTC",
            exchange="binance",
            interval="1h",
            open=close,
            high=close + Decimal("2"),
            low=close - Decimal("2"),
            close=close,
            volume=Decimal("1"),
            quote_volume=close,
        )
        for index, close in enumerate(closes)
    ]
