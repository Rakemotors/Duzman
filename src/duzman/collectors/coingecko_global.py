"""CoinGecko Global API collector for public BTC dominance."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any, Protocol

import httpx

from duzman.collectors.records import GlobalMetricRecord
from duzman.logging_config import get_logger, log_event, safe_error_message


COINGECKO_SOURCE = "coingecko"
BTC_DOMINANCE_METRIC_NAME = "btc_dominance"
COINGECKO_GLOBAL_USER_AGENT = "Duzman/0.1"
MAX_COINGECKO_GLOBAL_ERROR_LENGTH = 200


class CoinGeckoGlobalSourceHealthRecorder(Protocol):
    """Minimal source-health recorder interface used by CoinGeckoGlobalCollector."""

    def mark_success(self, source: str) -> object:
        """Record a successful public source check."""

    def mark_failure(self, source: str, error: str) -> object:
        """Record a failed public source check with a bounded error message."""


class CoinGeckoGlobalCollectorError(Exception):
    """Controlled error for one CoinGecko Global API request."""


class CoinGeckoGlobalCollector:
    """Fetch BTC dominance from CoinGecko's public global market endpoint."""

    source = COINGECKO_SOURCE
    url = "https://api.coingecko.com/api/v3/global"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 15.0,
        health_recorder: CoinGeckoGlobalSourceHealthRecorder | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": COINGECKO_GLOBAL_USER_AGENT},
        )
        self.timeout_seconds = timeout_seconds
        self.health_recorder = health_recorder
        self.logger = get_logger(__name__)

    async def fetch_btc_dominance(self) -> GlobalMetricRecord | None:
        """Fetch BTC dominance percentage as a normalized global metric."""
        started_at = monotonic()
        try:
            response = await self.client.get(
                self.url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": COINGECKO_GLOBAL_USER_AGENT},
            )
            if not 200 <= response.status_code < 300:
                raise CoinGeckoGlobalCollectorError(
                    f"CoinGecko global request returned status {response.status_code}"
                )
            payload = response.json()
            record = self._record_from_payload(payload)
        except Exception as exc:
            bounded_message = safe_error_message(
                exc,
                MAX_COINGECKO_GLOBAL_ERROR_LENGTH,
            )
            log_event(
                self.logger,
                "coingecko_global_schema_mismatch",
                level=logging.ERROR,
                safe_error_message=bounded_message,
            )
            await self._record_failure(bounded_message)
            return None

        await self._record_success()
        log_event(
            self.logger,
            "coingecko_global_fetch_success",
            metric_name=BTC_DOMINANCE_METRIC_NAME,
            latency_ms=self._elapsed_ms(started_at),
        )
        return record

    def _record_from_payload(self, payload: object) -> GlobalMetricRecord:
        if not isinstance(payload, Mapping):
            raise CoinGeckoGlobalCollectorError("CoinGecko global response must be a JSON object")
        data = payload.get("data")
        if not isinstance(data, Mapping):
            self._log_schema_mismatch(payload)
            raise CoinGeckoGlobalCollectorError("CoinGecko global response is missing data")
        market_cap_percentage = data.get("market_cap_percentage")
        if not isinstance(market_cap_percentage, Mapping):
            self._log_schema_mismatch(data)
            raise CoinGeckoGlobalCollectorError(
                "CoinGecko global response is missing market_cap_percentage"
            )
        if "btc" not in market_cap_percentage:
            self._log_schema_mismatch(market_cap_percentage)
            raise CoinGeckoGlobalCollectorError("CoinGecko global response is missing btc dominance")
        try:
            value = Decimal(str(market_cap_percentage["btc"]))
        except (InvalidOperation, ValueError) as exc:
            raise CoinGeckoGlobalCollectorError(
                "CoinGecko global response has invalid btc dominance"
            ) from exc
        return GlobalMetricRecord(
            ts=datetime.now(timezone.utc),
            metric_name=BTC_DOMINANCE_METRIC_NAME,
            value=value,
        )

    def _log_schema_mismatch(self, mapping: Mapping[str, Any]) -> None:
        log_event(
            self.logger,
            "coingecko_global_schema_mismatch",
            keys_found=list(mapping.keys()),
        )

    async def _record_success(self) -> None:
        if self.health_recorder is None:
            return
        result = self.health_recorder.mark_success(self.source)
        if inspect.isawaitable(result):
            await result

    async def _record_failure(self, error_message: str) -> None:
        if self.health_recorder is None:
            return
        result = self.health_recorder.mark_failure(
            self.source,
            safe_error_message(error_message, MAX_COINGECKO_GLOBAL_ERROR_LENGTH),
        )
        if inspect.isawaitable(result):
            await result

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
