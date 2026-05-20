import asyncio
from collections.abc import Coroutine
from datetime import datetime
from typing import Any, Mapping

from duzman.collectors import (
    BinanceCollector,
    CoinGeckoCollector,
    MarketDataPayloadError,
    MarketDataSnapshot,
)
from duzman.services.public_http_client import PublicHttpClient


class PublicMarketDataFetcher:
    """Fetch public market data and normalize it through existing collectors."""

    def __init__(
        self,
        http_client: PublicHttpClient | None = None,
        binance_collector: BinanceCollector | None = None,
        coingecko_collector: CoinGeckoCollector | None = None,
    ) -> None:
        self.http_client = http_client or PublicHttpClient()
        self.binance_collector = binance_collector or BinanceCollector()
        self.coingecko_collector = coingecko_collector or CoinGeckoCollector()

    def fetch_binance_ticker(
        self, symbol: str, collected_at: datetime | None = None
    ) -> MarketDataSnapshot:
        """Fetch and normalize one Binance public 24hr ticker response."""
        snapshots = self._run_binance_fetch(self.binance_collector.fetch_tickers([symbol]))
        if len(snapshots) != 1:
            raise RuntimeError("Binance public ticker fetch returned no snapshot")
        snapshot = snapshots[0]
        if collected_at is None:
            return snapshot
        return MarketDataSnapshot(
            source=snapshot.source,
            asset=snapshot.asset,
            quote_currency=snapshot.quote_currency,
            price_usd=snapshot.price_usd,
            ts=collected_at,
            raw_payload=snapshot.raw_payload,
            volume_24h_quote=snapshot.volume_24h_quote,
            price_change_24h_pct=snapshot.price_change_24h_pct,
        )

    def fetch_coingecko_market(
        self, coin_id: str, collected_at: datetime | None = None
    ) -> MarketDataSnapshot:
        """Fetch and normalize one CoinGecko public market response."""
        request = self.coingecko_collector.build_markets_request([coin_id])
        payload = self.http_client.get_json(request.url, request.params)
        market_item = self._single_coingecko_market_item(payload)
        return self.coingecko_collector.parse_market_payload(market_item, collected_at)

    def _single_coingecko_market_item(self, payload: Any) -> Mapping[str, Any]:
        if not isinstance(payload, list) or len(payload) != 1:
            raise MarketDataPayloadError(
                "CoinGecko public market payload must contain exactly one item"
            )
        market_item = payload[0]
        if not isinstance(market_item, Mapping):
            raise MarketDataPayloadError("CoinGecko market item must be an object")
        return market_item

    def _run_binance_fetch(
        self,
        coroutine: Coroutine[Any, Any, list[MarketDataSnapshot]],
    ) -> list[MarketDataSnapshot]:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)
        coroutine.close()
        raise RuntimeError(
            "Synchronous market data fetcher cannot run Binance async collector inside an active event loop"
        )
