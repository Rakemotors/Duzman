"""Bybit public derivatives collector for Stage A market metrics."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any, Protocol

import httpx

from duzman.logging_config import get_logger, log_event, safe_error_message


BYBIT_SOURCE = "bybit"
BYBIT_CATEGORY_LINEAR = "linear"
BYBIT_RATIO_TYPE_GLOBAL_ACCOUNTS = "global_accounts"
MAX_BYBIT_ERROR_LENGTH = 200


@dataclass(frozen=True)
class FundingRateRecord:
    """Normalized Bybit funding-rate row matching the DB model fields."""

    ts: datetime
    asset: str
    exchange: str
    funding_rate_pct: Decimal
    next_funding_time: datetime | None
    predicted_rate: Decimal | None = None


@dataclass(frozen=True)
class OpenInterestRecord:
    """Normalized Bybit open-interest row matching the DB model fields."""

    ts: datetime
    asset: str
    exchange: str
    oi_usd: Decimal
    oi_contracts: Decimal


@dataclass(frozen=True)
class LongShortRatioRecord:
    """Normalized Bybit long/short ratio row matching the DB model fields."""

    ts: datetime
    asset: str
    exchange: str
    ratio_type: str
    long_pct: float
    short_pct: float
    ratio: float


class BybitSourceHealthRecorder(Protocol):
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


class BybitCollectorError(Exception):
    """Controlled error for one Bybit public request attempt."""


class BybitCollector:
    """Fetch and normalize Bybit v5 public derivatives metrics."""

    source = BYBIT_SOURCE
    base_url = "https://api.bybit.com"
    supported_symbols: dict[str, str] = {
        "BTC": "BTCUSDT",
        "ETH": "ETHUSDT",
        "SOL": "SOLUSDT",
        "SUI": "SUIUSDT",
        "TON": "TONUSDT",
        "UNI": "UNIUSDT",
    }

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
        health_recorder: BybitSourceHealthRecorder | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds
        self.health_recorder = health_recorder
        self.logger = get_logger(__name__)

    async def fetch_funding_rates(self, symbols: list[str]) -> list[FundingRateRecord]:
        """Fetch public Bybit funding rates for Stage A asset symbols."""
        log_event(self.logger, "bybit_fetch_funding_started", symbol_count=len(symbols))
        records: list[FundingRateRecord] = []
        for symbol in symbols:
            record = await self._fetch_symbol_funding_rate(symbol)
            if record is not None:
                records.append(record)
        log_event(
            self.logger,
            "bybit_fetch_funding_completed",
            symbol_count=len(symbols),
            record_count=len(records),
        )
        return records

    async def fetch_open_interest(self, symbols: list[str]) -> list[OpenInterestRecord]:
        """Fetch public Bybit open interest for Stage A asset symbols."""
        log_event(
            self.logger,
            "bybit_fetch_open_interest_started",
            symbol_count=len(symbols),
        )
        records: list[OpenInterestRecord] = []
        for symbol in symbols:
            record = await self._fetch_symbol_open_interest(symbol)
            if record is not None:
                records.append(record)
        log_event(
            self.logger,
            "bybit_fetch_open_interest_completed",
            symbol_count=len(symbols),
            record_count=len(records),
        )
        return records

    async def fetch_long_short_ratio(
        self, symbols: list[str]
    ) -> list[LongShortRatioRecord]:
        """Fetch public Bybit global-account long/short ratios."""
        log_event(
            self.logger,
            "bybit_fetch_long_short_ratio_started",
            symbol_count=len(symbols),
        )
        records: list[LongShortRatioRecord] = []
        for symbol in symbols:
            record = await self._fetch_symbol_long_short_ratio(symbol)
            if record is not None:
                records.append(record)
        log_event(
            self.logger,
            "bybit_fetch_long_short_ratio_completed",
            symbol_count=len(symbols),
            record_count=len(records),
        )
        return records

    async def _fetch_symbol_funding_rate(
        self, symbol: str
    ) -> FundingRateRecord | None:
        started_at = monotonic()
        try:
            asset_symbol, bybit_symbol = self._normalize_asset_symbol(symbol)
            payload = await self._get_ticker_payload(bybit_symbol)
            ticker = self._single_result_item(payload)
            if ticker is None:
                await self._record_failure(
                    "Bybit ticker result.list was empty",
                    started_at,
                )
                return None
            funding_rate_fraction = self._required_decimal(ticker, "fundingRate")
            record = FundingRateRecord(
                ts=datetime.now(timezone.utc),
                asset=asset_symbol,
                exchange=self.source,
                funding_rate_pct=funding_rate_fraction * Decimal("100"),
                next_funding_time=self._optional_datetime_ms(ticker, "nextFundingTime"),
            )
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_BYBIT_ERROR_LENGTH),
                started_at,
            )
            return None

        await self._record_success(started_at)
        return record

    async def _fetch_symbol_open_interest(
        self, symbol: str
    ) -> OpenInterestRecord | None:
        started_at = monotonic()
        try:
            asset_symbol, bybit_symbol = self._normalize_asset_symbol(symbol)
            ticker_payload = await self._get_ticker_payload(bybit_symbol)
            ticker = self._single_result_item(ticker_payload)
            if ticker is None:
                await self._record_failure(
                    "Bybit ticker result.list was empty",
                    started_at,
                )
                return None
            mark_price = self._required_decimal(ticker, "markPrice")

            payload = await self._get_open_interest_payload(bybit_symbol)
            item = self._single_result_item(payload)
            if item is None:
                await self._record_failure(
                    "Bybit open interest result.list was empty",
                    started_at,
                )
                return None
            oi_contracts = self._required_decimal(item, "openInterest")
            record = OpenInterestRecord(
                ts=datetime.now(timezone.utc),
                asset=asset_symbol,
                exchange=self.source,
                oi_usd=oi_contracts * mark_price,
                oi_contracts=oi_contracts,
            )
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_BYBIT_ERROR_LENGTH),
                started_at,
            )
            return None

        await self._record_success(started_at)
        return record

    async def _fetch_symbol_long_short_ratio(
        self, symbol: str
    ) -> LongShortRatioRecord | None:
        started_at = monotonic()
        try:
            asset_symbol, bybit_symbol = self._normalize_asset_symbol(symbol)
            payload = await self._get_account_ratio_payload(bybit_symbol)
            item = self._single_result_item(payload)
            if item is None:
                await self._record_failure(
                    "Bybit account ratio result.list was empty",
                    started_at,
                )
                return None
            buy_ratio = self._required_decimal(item, "buyRatio")
            sell_ratio = self._required_decimal(item, "sellRatio")
            if sell_ratio == 0:
                raise BybitCollectorError("Bybit sellRatio must be greater than zero")
            record = LongShortRatioRecord(
                ts=datetime.now(timezone.utc),
                asset=asset_symbol,
                exchange=self.source,
                ratio_type=BYBIT_RATIO_TYPE_GLOBAL_ACCOUNTS,
                long_pct=float(buy_ratio * Decimal("100")),
                short_pct=float(sell_ratio * Decimal("100")),
                ratio=float(buy_ratio / sell_ratio),
            )
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_BYBIT_ERROR_LENGTH),
                started_at,
            )
            return None

        await self._record_success(started_at)
        return record

    async def _get_ticker_payload(self, bybit_symbol: str) -> Mapping[str, Any]:
        return await self._get_json(
            "/v5/market/tickers",
            {"category": BYBIT_CATEGORY_LINEAR, "symbol": bybit_symbol},
        )

    async def _get_open_interest_payload(self, bybit_symbol: str) -> Mapping[str, Any]:
        return await self._get_json(
            "/v5/market/open-interest",
            {
                "category": BYBIT_CATEGORY_LINEAR,
                "symbol": bybit_symbol,
                "intervalTime": "1h",
                "limit": "1",
            },
        )

    async def _get_account_ratio_payload(self, bybit_symbol: str) -> Mapping[str, Any]:
        return await self._get_json(
            "/v5/market/account-ratio",
            {
                "category": BYBIT_CATEGORY_LINEAR,
                "symbol": bybit_symbol,
                "period": "1h",
                "limit": "1",
            },
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
            raise BybitCollectorError("Bybit public request timed out") from exc
        except httpx.HTTPError as exc:
            raise BybitCollectorError("Bybit public request failed") from exc

        if not 200 <= response.status_code < 300:
            raise BybitCollectorError(
                f"Bybit public request returned status {response.status_code}"
            )

        payload = response.json()
        if not isinstance(payload, Mapping):
            raise BybitCollectorError("Bybit response must be a JSON object")
        ret_code = payload.get("retCode")
        if ret_code != 0:
            ret_message = str(payload.get("retMsg") or "unknown error")
            raise BybitCollectorError(f"Bybit retCode={ret_code}: {ret_message}")
        return payload

    def _single_result_item(self, payload: Mapping[str, Any]) -> Mapping[str, Any] | None:
        result = payload.get("result")
        if not isinstance(result, Mapping):
            raise BybitCollectorError("Bybit response is missing result object")
        result_list = result.get("list")
        if not isinstance(result_list, list):
            raise BybitCollectorError("Bybit response is missing result.list")
        if not result_list:
            return None
        item = result_list[-1]
        if not isinstance(item, Mapping):
            raise BybitCollectorError("Bybit result.list item must be an object")
        return item

    def _normalize_asset_symbol(self, symbol: str) -> tuple[str, str]:
        asset_symbol = symbol.upper()
        if asset_symbol not in self.supported_symbols:
            raise BybitCollectorError(f"Bybit asset is not supported for Stage A: {symbol}")
        return asset_symbol, self.supported_symbols[asset_symbol]

    def _required_decimal(self, payload: Mapping[str, Any], field_name: str) -> Decimal:
        value = payload.get(field_name)
        if value is None:
            raise BybitCollectorError(f"Bybit payload is missing decimal field: {field_name}")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise BybitCollectorError(
                f"Bybit payload has invalid decimal field: {field_name}"
            ) from exc

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
            raise BybitCollectorError(
                f"Bybit payload has invalid timestamp field: {field_name}"
            ) from exc
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

    async def _record_success(self, started_at: float) -> None:
        if self.health_recorder is None:
            return
        result = self.health_recorder.record_success(self.source, self._elapsed_ms(started_at))
        if inspect.isawaitable(result):
            await result

    async def _record_failure(self, error_message: str, started_at: float) -> None:
        bounded_message = safe_error_message(error_message, MAX_BYBIT_ERROR_LENGTH)
        log_event(
            self.logger,
            "bybit_fetch_failed",
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
