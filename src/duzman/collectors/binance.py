from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from duzman.collectors.base import (
    MarketDataPayloadError,
    MarketDataRequest,
    MarketDataSnapshot,
    UnsupportedMarketSymbolError,
)


class BinanceCollector:
    """Build and parse Binance public spot-market ticker data."""

    source = "binance"
    base_url = "https://api.binance.com"
    supported_symbols = {
        "BTCUSDT": ("BTC", "USDT"),
        "ETHUSDT": ("ETH", "USDT"),
    }

    def build_ticker_request(self, symbol: str) -> MarketDataRequest:
        """Return the deterministic public ticker request for a symbol."""
        normalized_symbol = self._normalize_symbol(symbol)
        return MarketDataRequest(
            method="GET",
            url=f"{self.base_url}/api/v3/ticker/24hr",
            params={"symbol": normalized_symbol},
        )

    def parse_ticker_payload(
        self,
        payload: Mapping[str, Any],
        collected_at: datetime | None = None,
    ) -> MarketDataSnapshot:
        """Normalize a Binance 24hr ticker payload into a market snapshot."""
        symbol = self._require_text(payload, "symbol")
        normalized_symbol = self._normalize_symbol(symbol)
        asset_symbol, quote_currency = self.supported_symbols[normalized_symbol]
        observed_at = collected_at or datetime.now(timezone.utc)

        return MarketDataSnapshot(
            source=self.source,
            symbol=asset_symbol,
            quote_currency=quote_currency,
            price=self._require_decimal(payload, "lastPrice"),
            collected_at=observed_at,
            raw_payload=dict(payload),
            volume_24h_quote=self._optional_decimal(payload, "quoteVolume"),
            price_change_24h_pct=self._optional_decimal(payload, "priceChangePercent"),
        )

    def _normalize_symbol(self, symbol: str) -> str:
        normalized_symbol = symbol.upper()
        if normalized_symbol not in self.supported_symbols:
            raise UnsupportedMarketSymbolError(
                f"Binance symbol is not supported for Stage A: {symbol}"
            )
        return normalized_symbol

    def _require_text(self, payload: Mapping[str, Any], field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise MarketDataPayloadError(
                f"Binance payload is missing text field: {field_name}"
            )
        return value

    def _require_decimal(
        self, payload: Mapping[str, Any], field_name: str
    ) -> Decimal:
        value = self._optional_decimal(payload, field_name)
        if value is None:
            raise MarketDataPayloadError(
                f"Binance payload is missing decimal field: {field_name}"
            )
        return value

    def _optional_decimal(
        self, payload: Mapping[str, Any], field_name: str
    ) -> Decimal | None:
        value = payload.get(field_name)
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise MarketDataPayloadError(
                f"Binance payload has invalid decimal field: {field_name}"
            ) from exc

