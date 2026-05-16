"""Tests for deterministic realized volatility calculations."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from duzman.collectors import OHLCVRecord
from duzman.indicators import compute_realized_volatility_24h


def test_compute_realized_volatility_24h_happy_path_has_known_result():
    """Realized volatility should match the deterministic 24h test series."""
    closes = [Decimal("100") + Decimal(index) for index in range(25)]

    assert compute_realized_volatility_24h(_candles(closes)) == Decimal("411.7611")


def test_compute_realized_volatility_24h_returns_none_when_data_is_insufficient():
    """Realized volatility needs at least 25 hourly candles for 24 returns."""
    closes = [Decimal("100") + Decimal(index) for index in range(24)]

    assert compute_realized_volatility_24h(_candles(closes)) is None


def test_compute_realized_volatility_24h_returns_zero_for_flat_closes():
    """Flat close prices should produce zero realized volatility."""
    closes = [Decimal("100") for _ in range(25)]

    assert compute_realized_volatility_24h(_candles(closes)) == Decimal("0.0000")


def _candles(closes: list[Decimal]) -> list[OHLCVRecord]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        OHLCVRecord(
            ts=base_time + timedelta(hours=index),
            asset="BTC",
            exchange="binance",
            interval="1h",
            open=close,
            high=close,
            low=close,
            close=close,
            volume=Decimal("1"),
            quote_volume=close,
        )
        for index, close in enumerate(closes)
    ]
