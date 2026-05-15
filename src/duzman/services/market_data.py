from datetime import datetime
from typing import Any, Iterable, Mapping

from duzman.collectors import BinanceCollector, CoinGeckoCollector, MarketDataSnapshot


class MarketDataService:
    """Normalize public market data payloads from supported Stage A sources."""

    def __init__(
        self,
        binance_collector: BinanceCollector | None = None,
        coingecko_collector: CoinGeckoCollector | None = None,
    ) -> None:
        self.binance_collector = binance_collector or BinanceCollector()
        self.coingecko_collector = coingecko_collector or CoinGeckoCollector()

    def normalize_binance_tickers(
        self,
        payloads: Iterable[Mapping[str, Any]],
        collected_at: datetime | None = None,
    ) -> list[MarketDataSnapshot]:
        """Normalize Binance ticker payloads supplied by a caller or test."""
        return [
            self.binance_collector.parse_ticker_payload(payload, collected_at)
            for payload in payloads
        ]

    def normalize_coingecko_markets(
        self,
        payloads: Iterable[Mapping[str, Any]],
        collected_at: datetime | None = None,
    ) -> list[MarketDataSnapshot]:
        """Normalize CoinGecko market payloads supplied by a caller or test."""
        return [
            self.coingecko_collector.parse_market_payload(payload, collected_at)
            for payload in payloads
        ]

