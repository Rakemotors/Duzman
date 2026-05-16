"""Alternative.me collector for the public Fear & Greed Index."""

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


ALTERNATIVE_ME_SOURCE = "alternative_me"
FEAR_GREED_METRIC_NAME = "fear_greed_index"
ALTERNATIVE_ME_USER_AGENT = "Duzman/0.1"
MAX_ALTERNATIVE_ME_ERROR_LENGTH = 200


class AlternativeMeSourceHealthRecorder(Protocol):
    """Minimal source-health recorder interface used by AlternativeMeCollector."""

    def mark_success(self, source: str) -> object:
        """Record a successful public source check."""

    def mark_failure(self, source: str, error: str) -> object:
        """Record a failed public source check with a bounded error message."""


class AlternativeMeCollectorError(Exception):
    """Controlled error for one Alternative.me Fear & Greed request."""


class AlternativeMeCollector:
    """Fetch Fear & Greed Index from Alternative.me public API."""

    source = ALTERNATIVE_ME_SOURCE
    url = "https://api.alternative.me/fng/?limit=1"

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 15.0,
        health_recorder: AlternativeMeSourceHealthRecorder | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": ALTERNATIVE_ME_USER_AGENT},
        )
        self.timeout_seconds = timeout_seconds
        self.health_recorder = health_recorder
        self.logger = get_logger(__name__)

    async def fetch_fear_greed(self) -> GlobalMetricRecord | None:
        """Fetch current Fear & Greed Index as a normalized global metric."""
        started_at = monotonic()
        try:
            response = await self.client.get(
                self.url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": ALTERNATIVE_ME_USER_AGENT},
            )
            if not 200 <= response.status_code < 300:
                raise AlternativeMeCollectorError(
                    f"Alternative.me request returned status {response.status_code}"
                )
            payload = response.json()
            record = self._record_from_payload(payload)
        except Exception as exc:
            bounded_message = safe_error_message(
                exc,
                MAX_ALTERNATIVE_ME_ERROR_LENGTH,
            )
            log_event(
                self.logger,
                "alternative_me_schema_mismatch",
                level=logging.ERROR,
                safe_error_message=bounded_message,
            )
            await self._record_failure(bounded_message)
            return None

        await self._record_success()
        log_event(
            self.logger,
            "alternative_me_fetch_success",
            metric_name=FEAR_GREED_METRIC_NAME,
            latency_ms=self._elapsed_ms(started_at),
        )
        return record

    def _record_from_payload(self, payload: object) -> GlobalMetricRecord:
        if not isinstance(payload, Mapping):
            raise AlternativeMeCollectorError("Alternative.me response must be a JSON object")
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            self._log_schema_mismatch(payload)
            raise AlternativeMeCollectorError("Alternative.me response has empty data")
        item = data[0]
        if not isinstance(item, Mapping) or "value" not in item:
            self._log_schema_mismatch(item if isinstance(item, Mapping) else payload)
            raise AlternativeMeCollectorError("Alternative.me response is missing value")
        try:
            value = Decimal(str(item["value"]))
        except (InvalidOperation, ValueError) as exc:
            raise AlternativeMeCollectorError(
                "Alternative.me response has invalid fear greed value"
            ) from exc
        return GlobalMetricRecord(
            ts=datetime.now(timezone.utc),
            metric_name=FEAR_GREED_METRIC_NAME,
            value=value,
        )

    def _log_schema_mismatch(self, mapping: Mapping[str, Any]) -> None:
        log_event(
            self.logger,
            "alternative_me_schema_mismatch",
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
            safe_error_message(error_message, MAX_ALTERNATIVE_ME_ERROR_LENGTH),
        )
        if inspect.isawaitable(result):
            await result

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
