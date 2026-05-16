"""Shared helpers for deterministic indicator calculations."""

from __future__ import annotations

from decimal import Decimal


INDICATOR_VALUE_QUANT = Decimal("0.0001")


def quantize_indicator_value(value: Decimal) -> Decimal:
    """Round an indicator value to the database value scale."""
    return value.quantize(INDICATOR_VALUE_QUANT)
