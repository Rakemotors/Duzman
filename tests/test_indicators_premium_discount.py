"""Tests for deterministic premium and discount calculations."""

from decimal import Decimal

from duzman.indicators import compute_premium_discount


def test_compute_premium_discount_returns_positive_premium():
    """Perp price above spot should return a positive premium percent."""
    assert compute_premium_discount(Decimal("110"), Decimal("100")) == Decimal("10.0000")


def test_compute_premium_discount_returns_negative_discount():
    """Perp price below spot should return a negative discount percent."""
    assert compute_premium_discount(Decimal("95"), Decimal("100")) == Decimal("-5.0000")


def test_compute_premium_discount_returns_zero_for_equal_prices():
    """Equal perp and spot prices should return zero premium."""
    assert compute_premium_discount(Decimal("100"), Decimal("100")) == Decimal("0.0000")
