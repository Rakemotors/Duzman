"""Premium and discount calculation for perpetual and spot prices."""

from __future__ import annotations

from decimal import Decimal

from duzman.indicators.common import quantize_indicator_value


def compute_premium_discount(perp_price: Decimal, spot_price: Decimal) -> Decimal:
    """Return the perp premium or discount versus spot in percent."""
    if spot_price == 0:
        raise ValueError("spot_price must be greater than zero")
    return quantize_indicator_value(((perp_price - spot_price) / spot_price) * Decimal("100"))
