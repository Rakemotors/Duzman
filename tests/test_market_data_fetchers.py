from datetime import datetime, timezone
from decimal import Decimal

import httpx

from duzman.services import PublicHttpClient, PublicMarketDataFetcher


def test_binance_public_fetcher_uses_request_definition_and_normalizes_payload():
    """Binance fetcher should use the public ticker request and fake HTTP payload."""
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "lastPrice": "67123.45",
                "quoteVolume": "123456789.12",
                "priceChangePercent": "2.345",
            },
        )

    fetcher = PublicMarketDataFetcher(
        http_client=PublicHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    )
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)

    snapshot = fetcher.fetch_binance_ticker("BTCUSDT", collected_at)

    assert observed_requests[0].url.path == "/api/v3/ticker/24hr"
    assert observed_requests[0].url.params["symbol"] == "BTCUSDT"
    assert snapshot.source == "binance"
    assert snapshot.symbol == "BTC"
    assert snapshot.price == Decimal("67123.45")


def test_coingecko_public_fetcher_uses_request_definition_and_normalizes_payload():
    """CoinGecko fetcher should use public markets request and fake HTTP payload."""
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "id": "ethereum",
                    "symbol": "eth",
                    "current_price": 3123.45,
                    "total_volume": 987654321.12,
                    "price_change_percentage_24h": -1.25,
                }
            ],
        )

    fetcher = PublicMarketDataFetcher(
        http_client=PublicHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    )
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)

    snapshot = fetcher.fetch_coingecko_market("ethereum", collected_at)

    assert observed_requests[0].url.path == "/api/v3/coins/markets"
    assert observed_requests[0].url.params["ids"] == "ethereum"
    assert observed_requests[0].url.params["vs_currency"] == "usd"
    assert snapshot.source == "coingecko"
    assert snapshot.symbol == "ETH"
    assert snapshot.price == Decimal("3123.45")

