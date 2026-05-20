from datetime import datetime, timezone
from decimal import Decimal

import pytest

from duzman.collectors import (
    CoinGeckoCollector,
    MarketDataPayloadError,
    UnsupportedMarketSymbolError,
)


def test_coingecko_builds_public_markets_request():
    """CoinGecko requests should use public market data without API keys."""
    request = CoinGeckoCollector().build_markets_request(["bitcoin", "ethereum"])

    assert request.method == "GET"
    assert request.url == "https://api.coingecko.com/api/v3/coins/markets"
    assert request.params == {
        "vs_currency": "usd",
        "ids": "bitcoin,ethereum",
        "price_change_percentage": "24h",
    }


def test_coingecko_valid_market_payload_parses_to_snapshot():
    """A valid CoinGecko market item should normalize Decimal values."""
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)
    payload = {
        "id": "ethereum",
        "symbol": "eth",
        "current_price": 3123.45,
        "total_volume": 987654321.12,
        "price_change_percentage_24h": -1.25,
    }

    snapshot = CoinGeckoCollector().parse_market_payload(payload, collected_at)

    assert snapshot.source == "coingecko"
    assert snapshot.asset == "ETH"
    assert snapshot.quote_currency == "USD"
    assert snapshot.price_usd == Decimal("3123.45")
    assert snapshot.volume_24h_quote == Decimal("987654321.12")
    assert snapshot.price_change_24h_pct == Decimal("-1.25")
    assert snapshot.ts == collected_at
    assert snapshot.raw_payload == payload


def test_coingecko_malformed_payload_fails_with_clear_exception():
    """Missing required CoinGecko price fields should not be ignored."""
    payload = {"id": "bitcoin"}

    with pytest.raises(MarketDataPayloadError, match="current_price"):
        CoinGeckoCollector().parse_market_payload(payload)


def test_coingecko_unsupported_coin_id_is_rejected():
    """Only explicitly supported Stage A public coin IDs are accepted."""
    with pytest.raises(UnsupportedMarketSymbolError, match="not supported"):
        CoinGeckoCollector().build_markets_request(["ripple"])
