"""OKX public derivatives collector for Stage A market metrics."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any, Protocol

import httpx

from duzman.collectors.bybit import (
    FundingRateRecord,
    LongShortRatioRecord,
    OpenInterestRecord,
)
from duzman.logging_config import get_logger, log_event, safe_error_message


OKX_SOURCE = "okx"
OKX_INST_TYPE_SWAP = "SWAP"
OKX_RATIO_TYPE_GLOBAL_ACCOUNTS = "global_accounts"
MAX_OKX_ERROR_LENGTH = 200


class OKXSourceHealthRecorder(Protocol):
    """Minimal source-health recorder interface used by the collector."""

    def record_success(self, source: str, latency_ms: int) -> object:
        """Record a successful public source check."""

    def record_failure(
        self,
        source: str,
        error_message: str,
        latency_ms: int | None = None,
    ) -> object:
        """Record a failed public source check with a bounded error message."""


class OKXCollectorError(Exception):
    """Controlled error for one OKX public request attempt."""


class OKXCollector:
    """Fetch and normalize OKX v5 public derivatives metrics."""

    source = OKX_SOURCE
    base_url = "https://www.okx.com"
    supported_symbols: dict[str, str] = {
        "BTC": "BTC-USDT-SWAP",
        "ETH": "ETH-USDT-SWAP",
        "SOL": "SOL-USDT-SWAP",
        "SUI": "SUI-USDT-SWAP",
        "TON": "TON-USDT-SWAP",
        "UNI": "UNI-USDT-SWAP",
    }

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
        health_recorder: OKXSourceHealthRecorder | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds
        self.health_recorder = health_recorder
        self.logger = get_logger(__name__)

    async def fetch_funding_rates(self, symbols: list[str]) -> list[FundingRateRecord]:
        """Fetch public OKX funding rates for Stage A asset symbols."""
        log_event(self.logger, "okx_fetch_funding_started", symbol_count=len(symbols))
        records: list[FundingRateRecord] = []
        for symbol in symbols:
            record = await self._fetch_symbol_funding_rate(symbol)
            if record is not None:
                records.append(record)
        log_event(
            self.logger,
            "okx_fetch_funding_completed",
            symbol_count=len(symbols),
            record_count=len(records),
        )
        return records

    async def fetch_open_interest(self, symbols: list[str]) -> list[OpenInterestRecord]:
        """Fetch public OKX open interest for Stage A asset symbols."""
        log_event(
            self.logger,
            "okx_fetch_open_interest_started",
            symbol_count=len(symbols),
        )
        records: list[OpenInterestRecord] = []
        for symbol in symbols:
            record = await self._fetch_symbol_open_interest(symbol)
            if record is not None:
                records.append(record)
        log_event(
            self.logger,
            "okx_fetch_open_interest_completed",
            symbol_count=len(symbols),
            record_count=len(records),
        )
        return records

    async def fetch_long_short_ratio(
        self, symbols: list[str]
    ) -> list[LongShortRatioRecord]:
        """Fetch public OKX global-account long/short ratios."""
        log_event(
            self.logger,
            "okx_fetch_long_short_ratio_started",
            symbol_count=len(symbols),
        )
        records: list[LongShortRatioRecord] = []
        for symbol in symbols:
            record = await self._fetch_symbol_long_short_ratio(symbol)
            if record is not None:
                records.append(record)
        log_event(
            self.logger,
            "okx_fetch_long_short_ratio_completed",
            symbol_count=len(symbols),
            record_count=len(records),
        )
        return records

    async def _fetch_symbol_funding_rate(self, symbol: str) -> FundingRateRecord | None:
        started_at = monotonic()
        try:
            asset_symbol, instrument_id = self._normalize_asset_symbol(symbol)
            payload = await self._get_funding_rate_payload(instrument_id)
            item = self._single_data_item(payload)
            if item is None:
                await self._record_failure("OKX funding rate data was empty", started_at)
                return None
            funding_rate_fraction = self._required_decimal(item, "fundingRate")
            record = FundingRateRecord(
                ts=datetime.now(timezone.utc),
                asset=asset_symbol,
                exchange=self.source,
                funding_rate_pct=funding_rate_fraction * Decimal("100"),
                next_funding_time=self._optional_datetime_ms(item, "nextFundingTime"),
            )
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_OKX_ERROR_LENGTH),
                started_at,
            )
            return None

        await self._record_success(started_at)
        return record

    async def _fetch_symbol_open_interest(
        self,
        symbol: str,
    ) -> OpenInterestRecord | None:
        started_at = monotonic()
        try:
            asset_symbol, instrument_id = self._normalize_asset_symbol(symbol)
            mark_price_payload = await self._get_mark_price_payload(instrument_id)
            mark_price_item = self._single_data_item(mark_price_payload)
            if mark_price_item is None:
                await self._record_failure("OKX mark price data was empty", started_at)
                return None
            mark_price = self._required_decimal(mark_price_item, "markPx")

            payload = await self._get_open_interest_payload(instrument_id)
            item = self._single_data_item(payload)
            if item is None:
                await self._record_failure("OKX open interest data was empty", started_at)
                return None
            oi_contracts = self._required_decimal(item, "oi")
            record = OpenInterestRecord(
                ts=datetime.now(timezone.utc),
                asset=asset_symbol,
                exchange=self.source,
                oi_usd=oi_contracts * mark_price,
                oi_contracts=oi_contracts,
            )
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_OKX_ERROR_LENGTH),
                started_at,
            )
            return None

        await self._record_success(started_at)
        return record

    async def _fetch_symbol_long_short_ratio(
        self,
        symbol: str,
    ) -> LongShortRatioRecord | None:
        started_at = monotonic()
        try:
            asset_symbol, _instrument_id = self._normalize_asset_symbol(symbol)
            payload = await self._get_long_short_ratio_payload(asset_symbol)
            item = self._single_data_item(payload)
            if item is None:
                await self._record_failure("OKX long/short ratio data was empty", started_at)
                return None
            ratio_decimal = self._ratio_from_pair(item)
            if ratio_decimal <= 0:
                raise OKXCollectorError("OKX long/short ratio must be greater than zero")
            record = LongShortRatioRecord(
                ts=datetime.now(timezone.utc),
                asset=asset_symbol,
                exchange=self.source,
                ratio_type=OKX_RATIO_TYPE_GLOBAL_ACCOUNTS,
                long_pct=float((ratio_decimal / (Decimal("1") + ratio_decimal)) * Decimal("100")),
                short_pct=float((Decimal("1") / (Decimal("1") + ratio_decimal)) * Decimal("100")),
                ratio=float(ratio_decimal),
            )
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_OKX_ERROR_LENGTH),
                started_at,
            )
            return None

        await self._record_success(started_at)
        return record

    async def _get_funding_rate_payload(self, instrument_id: str) -> Mapping[str, Any]:
        return await self._get_json(
            "/api/v5/public/funding-rate",
            {"instId": instrument_id},
        )

    async def _get_mark_price_payload(self, instrument_id: str) -> Mapping[str, Any]:
        return await self._get_json(
            "/api/v5/public/mark-price",
            {"instId": instrument_id},
        )

    async def _get_open_interest_payload(self, instrument_id: str) -> Mapping[str, Any]:
        return await self._get_json(
            "/api/v5/public/open-interest",
            {"instType": OKX_INST_TYPE_SWAP, "instId": instrument_id},
        )

    async def _get_long_short_ratio_payload(self, asset_symbol: str) -> Mapping[str, Any]:
        return await self._get_json(
            "/api/v5/rubik/stat/contracts/long-short-account-ratio",
            {"ccy": asset_symbol, "period": "5m"},
        )

    async def _get_json(
        self,
        path: str,
        params: Mapping[str, str],
    ) -> Mapping[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.get(
                url,
                params=dict(params),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise OKXCollectorError("OKX public request timed out") from exc
        except httpx.HTTPError as exc:
            raise OKXCollectorError("OKX public request failed") from exc

        if not 200 <= response.status_code < 300:
            raise OKXCollectorError(
                f"OKX public request returned status {response.status_code}"
            )

        payload = response.json()
        if not isinstance(payload, Mapping):
            raise OKXCollectorError("OKX response must be a JSON object")
        code = str(payload.get("code"))
        if code != "0":
            message = str(payload.get("msg") or "unknown error")
            raise OKXCollectorError(f"OKX code={code}: {message}")
        return payload

    def _single_data_item(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | Sequence[Any] | None:
        data = payload.get("data")
        if not isinstance(data, list):
            raise OKXCollectorError("OKX response is missing data array")
        if not data:
            return None
        item = data[-1]
        if not isinstance(item, (Mapping, Sequence)) or isinstance(item, (str, bytes)):
            raise OKXCollectorError("OKX data item must be an object or array")
        return item

    def _normalize_asset_symbol(self, symbol: str) -> tuple[str, str]:
        asset_symbol = symbol.upper()
        if asset_symbol not in self.supported_symbols:
            raise OKXCollectorError(f"OKX asset is not supported for Stage A: {symbol}")
        return asset_symbol, self.supported_symbols[asset_symbol]

    def _required_decimal(self, payload: Mapping[str, Any], field_name: str) -> Decimal:
        value = payload.get(field_name)
        if value is None:
            raise OKXCollectorError(f"OKX payload is missing decimal field: {field_name}")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise OKXCollectorError(
                f"OKX payload has invalid decimal field: {field_name}"
            ) from exc

    def _ratio_from_pair(self, payload: Mapping[str, Any] | Sequence[Any]) -> Decimal:
        if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
            raise OKXCollectorError("OKX ratio data item must be an array")
        if len(payload) < 2:
            raise OKXCollectorError("OKX ratio data item is missing ratio")
        try:
            return Decimal(str(payload[1]))
        except (InvalidOperation, ValueError) as exc:
            raise OKXCollectorError("OKX ratio data item has invalid ratio") from exc

    def _optional_datetime_ms(
        self,
        payload: Mapping[str, Any],
        field_name: str,
    ) -> datetime | None:
        value = payload.get(field_name)
        if value in (None, ""):
            return None
        try:
            timestamp_ms = int(str(value))
        except ValueError as exc:
            raise OKXCollectorError(
                f"OKX payload has invalid timestamp field: {field_name}"
            ) from exc
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

    async def _record_success(self, started_at: float) -> None:
        if self.health_recorder is None:
            return
        result = self.health_recorder.record_success(self.source, self._elapsed_ms(started_at))
        if inspect.isawaitable(result):
            await result

    async def _record_failure(self, error_message: str, started_at: float) -> None:
        bounded_message = safe_error_message(error_message, MAX_OKX_ERROR_LENGTH)
        log_event(
            self.logger,
            "okx_fetch_failed",
            level=logging.ERROR,
            source=self.source,
            safe_error_message=bounded_message,
        )
        if self.health_recorder is None:
            return
        result = self.health_recorder.record_failure(
            self.source,
            bounded_message,
            self._elapsed_ms(started_at),
        )
        if inspect.isawaitable(result):
            await result

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
