from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping


class MarketDataCollectorError(Exception):
    """Base error for public market data collector failures."""


class MarketDataPayloadError(MarketDataCollectorError):
    """Raised when a public market data response is missing required fields."""


class UnsupportedMarketSymbolError(MarketDataCollectorError):
    """Raised when a collector is asked for an unsupported Stage A asset."""


@dataclass(frozen=True)
class MarketDataRequest:
    """Deterministic public-data request definition for a collector."""

    method: str
    url: str
    params: Mapping[str, str]


@dataclass(frozen=True)
class MarketDataSnapshot:
    """Normalized public market data snapshot used before DB persistence."""

    source: str
    symbol: str
    quote_currency: str
    price: Decimal
    collected_at: datetime
    raw_payload: Mapping[str, Any]
    volume_24h_quote: Decimal | None = None
    price_change_24h_pct: Decimal | None = None

