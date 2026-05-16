"""Tests for deterministic Stochastic oscillator calculations."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from duzman.collectors import OHLCVRecord
from duzman.indicators import compute_stochastic


def test_compute_stochastic_happy_path_has_known_result():
    """Stochastic should return the expected latest %K and %D values."""
    assert compute_stochastic(_variable_candles()) == (
        Decimal("71.5277"),
        Decimal("69.9301"),
    )


def test_compute_stochastic_returns_none_when_data_is_insufficient():
    """Stochastic should return None instead of raising for too few candles."""
    assert compute_stochastic(_variable_candles()[:10]) is None


def test_compute_stochastic_k_and_d_can_differ():
    """The latest %K and %D values should remain distinct when data supports it."""
    stochastic = compute_stochastic(_variable_candles())

    assert stochastic is not None
    assert stochastic[0] != stochastic[1]


def test_compute_stochastic_boundary_values_reach_zero_and_one_hundred():
    """Boundary candles should produce deterministic 0 and 100 oscillator values."""
    assert compute_stochastic(_flat_range_candles(close=Decimal("100"))) == (
        Decimal("100.0000"),
        Decimal("100.0000"),
    )
    assert compute_stochastic(_flat_range_candles(close=Decimal("0"))) == (
        Decimal("0.0000"),
        Decimal("0.0000"),
    )


def _variable_candles() -> list[OHLCVRecord]:
    closes = [
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
    return _candles_from_closes(closes)


def _flat_range_candles(close: Decimal) -> list[OHLCVRecord]:
    return _candles_from_closes([close for _ in range(20)], high=Decimal("100"), low=Decimal("0"))


def _candles_from_closes(
    closes: list[Decimal],
    high: Decimal | None = None,
    low: Decimal | None = None,
) -> list[OHLCVRecord]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        OHLCVRecord(
            ts=base_time + timedelta(hours=index),
            asset="BTC",
            exchange="binance",
            interval="1h",
            open=close,
            high=high if high is not None else close + Decimal("2"),
            low=low if low is not None else close - Decimal("2"),
            close=close,
            volume=Decimal("1"),
            quote_volume=close,
        )
        for index, close in enumerate(closes)
    ]
