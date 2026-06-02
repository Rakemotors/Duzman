import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from types import TracebackType

import httpx
import pytest

import duzman.collectors.binance as binance_module
from duzman.collectors import BinanceCollector
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
        binance_collector=BinanceCollector(
            client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
        )
    )
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=UTC)

    snapshot = fetcher.fetch_binance_ticker("BTCUSDT", collected_at)

    assert observed_requests[0].url.path == "/api/v3/ticker/24hr"
    assert observed_requests[0].url.params["symbol"] == "BTCUSDT"
    assert snapshot.source == "binance"
    assert snapshot.asset == "BTC"
    assert snapshot.price_usd == Decimal("67123.45")


def test_binance_public_fetcher_does_not_reuse_default_async_client_across_loops(
    monkeypatch,
):
    """Sequential sync Binance fetches should not reuse one async client across loops."""
    observed_symbols: list[str] = []

    class LoopBoundAsyncClient:
        """Fake async client that fails if reused by a different event loop."""

        def __init__(self, timeout: float) -> None:
            self.timeout = timeout
            self._loop_id: int | None = None

        async def __aenter__(self) -> "LoopBoundAsyncClient":
            return self

        async def __aexit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            return None

        async def get(
            self,
            url: str,
            *,
            params: dict[str, str],
            **kwargs: object,
        ) -> httpx.Response:
            loop_id = id(asyncio.get_running_loop())
            if self._loop_id is None:
                self._loop_id = loop_id
            elif self._loop_id != loop_id:
                raise RuntimeError("Event loop is closed")
            observed_symbols.append(params["symbol"])
            return httpx.Response(
                200,
                json={
                    "symbol": params["symbol"],
                    "lastPrice": "67123.45",
                    "quoteVolume": "123456789.12",
                    "priceChangePercent": "2.345",
                },
            )

    monkeypatch.setattr(binance_module.httpx, "AsyncClient", LoopBoundAsyncClient)
    fetcher = PublicMarketDataFetcher()
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=UTC)

    btc = fetcher.fetch_binance_ticker("BTCUSDT", collected_at)
    eth = fetcher.fetch_binance_ticker("ETHUSDT", collected_at)

    assert observed_symbols == ["BTCUSDT", "ETHUSDT"]
    assert btc.asset == "BTC"
    assert eth.asset == "ETH"


def test_binance_public_fetcher_still_raises_when_collector_returns_no_snapshot():
    """Genuine Binance collector failures should keep source health failure semantics."""
    class EmptyBinanceCollector:
        """Fake collector that simulates a contained Binance source failure."""

        async def fetch_tickers(self, symbols: list[str]) -> list[object]:
            return []

    fetcher = PublicMarketDataFetcher(binance_collector=EmptyBinanceCollector())

    with pytest.raises(RuntimeError, match="returned no snapshot"):
        fetcher.fetch_binance_ticker("BTCUSDT")


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
    collected_at = datetime(2026, 5, 15, 12, 17, tzinfo=UTC)

    snapshot = fetcher.fetch_coingecko_market("ethereum", collected_at)

    assert observed_requests[0].url.path == "/api/v3/coins/markets"
    assert observed_requests[0].url.params["ids"] == "ethereum"
    assert observed_requests[0].url.params["vs_currency"] == "usd"
    assert snapshot.source == "coingecko"
    assert snapshot.asset == "ETH"
    assert snapshot.price_usd == Decimal("3123.45")
