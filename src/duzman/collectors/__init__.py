"""Public market data collectors for Duzman Stage A."""

from duzman.collectors.base import (
    MarketDataCollectorError,
    MarketDataPayloadError,
    MarketDataRequest,
    MarketDataSnapshot,
    UnsupportedMarketSymbolError,
)
from duzman.collectors.binance import BinanceCollector
from duzman.collectors.bybit import BybitCollector
from duzman.collectors.coingecko import CoinGeckoCollector
from duzman.collectors.okx import OKXCollector
from duzman.collectors.records import (
    FundingRateRecord,
    LongShortRatioRecord,
    OHLCVRecord,
    OpenInterestRecord,
)

__all__ = [
    "BinanceCollector",
    "BybitCollector",
    "CoinGeckoCollector",
    "FundingRateRecord",
    "LongShortRatioRecord",
    "MarketDataCollectorError",
    "MarketDataPayloadError",
    "MarketDataRequest",
    "MarketDataSnapshot",
    "OHLCVRecord",
    "OKXCollector",
    "OpenInterestRecord",
    "UnsupportedMarketSymbolError",
]
