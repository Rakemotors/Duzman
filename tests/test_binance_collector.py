from datetime import datetime, timezone
from decimal import Decimal

import pytest

from duzman.collectors import (
    BinanceCollector,
    MarketDataPayloadError,
    UnsupportedMarketSymbolError,
)


def test_binance_builds_public_ticker_request():
    """Binance requests must target public ticker data, not trading endpoints."""
    request = BinanceCollector().build_ticker_request("btcusdt")

    assert request.method == "GET"
    assert request.url == "https://api.binance.com/api/v3/ticker/24hr"
    assert request.params == {"symbol": "BTCUSDT"}
    assert "order" not in request.url
    assert "account" not in request.url


def test_binance_valid_ticker_payload_parses_to_snapshot():
    """A valid Binance ticker payload should normalize Decimal values."""
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)
    payload = {
        "symbol": "BTCUSDT",
        "lastPrice": "67123.45000000",
        "quoteVolume": "123456789.12000000",
        "priceChangePercent": "2.345",
    }

    snapshot = BinanceCollector().parse_ticker_payload(payload, collected_at)

    assert snapshot.source == "binance"
    assert snapshot.symbol == "BTC"
    assert snapshot.quote_currency == "USDT"
    assert snapshot.price == Decimal("67123.45000000")
    assert snapshot.volume_24h_quote == Decimal("123456789.12000000")
    assert snapshot.price_change_24h_pct == Decimal("2.345")
    assert snapshot.collected_at == collected_at
    assert snapshot.raw_payload == payload


def test_binance_malformed_payload_fails_with_clear_exception():
    """Missing required Binance price fields should not be ignored."""
    payload = {"symbol": "BTCUSDT"}

    with pytest.raises(MarketDataPayloadError, match="lastPrice"):
        BinanceCollector().parse_ticker_payload(payload)


def test_binance_unsupported_symbol_is_rejected():
    """Only explicitly supported Stage A public symbols are accepted."""
    with pytest.raises(UnsupportedMarketSymbolError, match="not supported"):
        BinanceCollector().build_ticker_request("XRPUSDT")

