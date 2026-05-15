from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from duzman.collectors.base import (
    MarketDataPayloadError,
    MarketDataRequest,
    MarketDataSnapshot,
    UnsupportedMarketSymbolError,
)


class CoinGeckoCollector:
    """Build and parse CoinGecko public market data responses."""

    source = "coingecko"
    base_url = "https://api.coingecko.com/api/v3"
    supported_coin_ids = {
        "bitcoin": "BTC",
        "ethereum": "ETH",
    }

    def build_markets_request(self, coin_ids: list[str]) -> MarketDataRequest:
        """Return the deterministic public markets request for supported coins."""
        normalized_ids = [self._normalize_coin_id(coin_id) for coin_id in coin_ids]
        return MarketDataRequest(
            method="GET",
            url=f"{self.base_url}/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ",".join(normalized_ids),
                "price_change_percentage": "24h",
            },
        )

    def parse_market_payload(
        self,
        payload: Mapping[str, Any],
        collected_at: datetime | None = None,
    ) -> MarketDataSnapshot:
        """Normalize one CoinGecko market item into a market snapshot."""
        coin_id = self._require_text(payload, "id")
        normalized_coin_id = self._normalize_coin_id(coin_id)
        observed_at = collected_at or datetime.now(timezone.utc)

        return MarketDataSnapshot(
            source=self.source,
            symbol=self.supported_coin_ids[normalized_coin_id],
            quote_currency="USD",
            price=self._require_decimal(payload, "current_price"),
            collected_at=observed_at,
            raw_payload=dict(payload),
            volume_24h_quote=self._optional_decimal(payload, "total_volume"),
            price_change_24h_pct=self._optional_decimal(
                payload, "price_change_percentage_24h"
            ),
        )

    def _normalize_coin_id(self, coin_id: str) -> str:
        normalized_coin_id = coin_id.lower()
        if normalized_coin_id not in self.supported_coin_ids:
            raise UnsupportedMarketSymbolError(
                f"CoinGecko coin ID is not supported for Stage A: {coin_id}"
            )
        return normalized_coin_id

    def _require_text(self, payload: Mapping[str, Any], field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise MarketDataPayloadError(
                f"CoinGecko payload is missing text field: {field_name}"
            )
        return value

    def _require_decimal(
        self, payload: Mapping[str, Any], field_name: str
    ) -> Decimal:
        value = self._optional_decimal(payload, field_name)
        if value is None:
            raise MarketDataPayloadError(
                f"CoinGecko payload is missing decimal field: {field_name}"
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
                f"CoinGecko payload has invalid decimal field: {field_name}"
            ) from exc

