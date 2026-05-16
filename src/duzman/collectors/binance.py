"""Binance public spot collector for Stage A ticker and OHLCV data."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any, Protocol

import httpx

from duzman.collectors.base import (
    MarketDataPayloadError,
    MarketDataSnapshot,
    UnsupportedMarketSymbolError,
)
from duzman.collectors.records import OHLCVRecord
from duzman.logging_config import get_logger, log_event, safe_error_message


BINANCE_SOURCE = "binance"
BINANCE_QUOTE_CURRENCY = "USDT"
MAX_BINANCE_ERROR_LENGTH = 200
SUPPORTED_BINANCE_INTERVALS: frozenset[str] = frozenset({"1h", "4h", "1d", "1w"})


class BinanceSourceHealthRecorder(Protocol):
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


class BinanceCollectorError(Exception):
    """Controlled error for one Binance public request attempt."""


class BinanceCollector:
    """Fetch and normalize Binance public spot ticker and OHLCV data."""

    source = BINANCE_SOURCE
    base_url = "https://api.binance.com"
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
        health_recorder: BinanceSourceHealthRecorder | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds
        self.health_recorder = health_recorder
        self.logger = get_logger(__name__)

    async def fetch_tickers(self, symbols: list[str]) -> list[MarketDataSnapshot]:
        """Fetch public Binance 24hr tickers for Stage A asset symbols."""
        log_event(
            self.logger,
            "binance_fetch_tickers_started",
            symbol_count=len(symbols),
        )
        snapshots: list[MarketDataSnapshot] = []
        for symbol in symbols:
            snapshot = await self._fetch_symbol_ticker(symbol)
            if snapshot is not None:
                snapshots.append(snapshot)
        log_event(
            self.logger,
            "binance_fetch_tickers_completed",
            symbol_count=len(symbols),
            snapshot_count=len(snapshots),
        )
        return snapshots

    async def fetch_ohlcv(
        self,
        symbol: str,
        interval: str,
        limit: int = 100,
    ) -> list[OHLCVRecord]:
        """Fetch public Binance OHLCV candles for one Stage A asset symbol."""
        started_at = monotonic()
        log_event(
            self.logger,
            "binance_fetch_ohlcv_started",
            symbol=symbol.upper(),
            interval=interval,
            limit=limit,
        )
        try:
            asset_symbol, binance_symbol = self._normalize_asset_symbol(symbol)
            self._validate_interval(interval)
            payload = await self._get_klines_payload(binance_symbol, interval, limit)
            records = [
                self._normalize_kline(asset_symbol, interval, item)
                for item in self._kline_items(payload)
            ]
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_BINANCE_ERROR_LENGTH),
                started_at,
            )
            return []

        await self._record_success(started_at)
        log_event(
            self.logger,
            "binance_fetch_ohlcv_completed",
            symbol=asset_symbol,
            interval=interval,
            record_count=len(records),
        )
        return records

    def normalize_ticker_payload(
        self,
        payload: Mapping[str, Any],
        collected_at: datetime | None = None,
    ) -> MarketDataSnapshot:
        """Normalize a supplied Binance ticker payload without making HTTP calls."""
        symbol = self._require_text(payload, "symbol")
        asset_symbol, _binance_symbol = self._normalize_asset_symbol(symbol)
        observed_at = collected_at or datetime.now(timezone.utc)

        return MarketDataSnapshot(
            source=self.source,
            symbol=asset_symbol,
            quote_currency=BINANCE_QUOTE_CURRENCY,
            price=self._required_decimal(payload, "lastPrice"),
            collected_at=observed_at,
            raw_payload=dict(payload),
            volume_24h_quote=self._optional_decimal(payload, "quoteVolume"),
            price_change_24h_pct=self._optional_decimal(payload, "priceChangePercent"),
        )

    async def _fetch_symbol_ticker(self, symbol: str) -> MarketDataSnapshot | None:
        started_at = monotonic()
        try:
            _asset_symbol, binance_symbol = self._normalize_asset_symbol(symbol)
            payload = await self._get_ticker_payload(binance_symbol)
            if not isinstance(payload, Mapping):
                raise BinanceCollectorError("Binance ticker response must be an object")
            snapshot = self.normalize_ticker_payload(payload)
        except Exception as exc:
            await self._record_failure(
                safe_error_message(exc, MAX_BINANCE_ERROR_LENGTH),
                started_at,
            )
            return None

        await self._record_success(started_at)
        return snapshot

    async def _get_ticker_payload(self, binance_symbol: str) -> Any:
        return await self._get_json(
            "/api/v3/ticker/24hr",
            {"symbol": binance_symbol},
        )

    async def _get_klines_payload(
        self,
        binance_symbol: str,
        interval: str,
        limit: int,
    ) -> Any:
        return await self._get_json(
            "/api/v3/klines",
            {"symbol": binance_symbol, "interval": interval, "limit": str(limit)},
        )

    async def _get_json(self, path: str, params: Mapping[str, str]) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = await self.client.get(
                url,
                params=dict(params),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise BinanceCollectorError("Binance public request timed out") from exc
        except httpx.HTTPError as exc:
            raise BinanceCollectorError("Binance public request failed") from exc

        if not 200 <= response.status_code < 300:
            raise BinanceCollectorError(
                f"Binance public request returned status {response.status_code}"
            )
        return response.json()

    def _normalize_asset_symbol(self, symbol: str) -> tuple[str, str]:
        normalized_symbol = symbol.upper()
        if normalized_symbol in self.supported_symbols:
            return normalized_symbol, self.supported_symbols[normalized_symbol]

        for asset_symbol, binance_symbol in self.supported_symbols.items():
            if normalized_symbol == binance_symbol:
                return asset_symbol, binance_symbol

        raise UnsupportedMarketSymbolError(
            f"Binance symbol is not supported for Stage A: {symbol}"
        )

    def _validate_interval(self, interval: str) -> None:
        if interval not in SUPPORTED_BINANCE_INTERVALS:
            raise BinanceCollectorError(
                f"Binance interval is not supported for Stage A: {interval}"
            )

    def _kline_items(self, payload: Any) -> list[Sequence[Any]]:
        if not isinstance(payload, list):
            raise BinanceCollectorError("Binance klines response must be an array")
        items: list[Sequence[Any]] = []
        for item in payload:
            if not isinstance(item, Sequence) or isinstance(item, (str, bytes)):
                raise BinanceCollectorError("Binance kline item must be an array")
            if len(item) < 8:
                raise BinanceCollectorError("Binance kline item has too few fields")
            items.append(item)
        return items

    def _normalize_kline(
        self,
        asset_symbol: str,
        interval: str,
        item: Sequence[Any],
    ) -> OHLCVRecord:
        return OHLCVRecord(
            ts=self._datetime_ms(item[6], "close_time"),
            asset=asset_symbol,
            exchange=self.source,
            interval=interval,
            open=self._decimal_value(item[1], "open"),
            high=self._decimal_value(item[2], "high"),
            low=self._decimal_value(item[3], "low"),
            close=self._decimal_value(item[4], "close"),
            volume=self._decimal_value(item[5], "volume"),
            quote_volume=self._decimal_value(item[7], "quote_volume"),
        )

    def _require_text(self, payload: Mapping[str, Any], field_name: str) -> str:
        value = payload.get(field_name)
        if not isinstance(value, str) or not value.strip():
            raise MarketDataPayloadError(
                f"Binance payload is missing text field: {field_name}"
            )
        return value

    def _required_decimal(self, payload: Mapping[str, Any], field_name: str) -> Decimal:
        value = self._optional_decimal(payload, field_name)
        if value is None:
            raise MarketDataPayloadError(
                f"Binance payload is missing decimal field: {field_name}"
            )
        return value

    def _optional_decimal(
        self,
        payload: Mapping[str, Any],
        field_name: str,
    ) -> Decimal | None:
        value = payload.get(field_name)
        if value is None:
            return None
        return self._decimal_value(value, field_name)

    def _decimal_value(self, value: Any, field_name: str) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise MarketDataPayloadError(
                f"Binance payload has invalid decimal field: {field_name}"
            ) from exc

    def _datetime_ms(self, value: Any, field_name: str) -> datetime:
        try:
            timestamp_ms = int(str(value))
        except ValueError as exc:
            raise MarketDataPayloadError(
                f"Binance payload has invalid timestamp field: {field_name}"
            ) from exc
        return datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)

    async def _record_success(self, started_at: float) -> None:
        if self.health_recorder is None:
            return
        result = self.health_recorder.record_success(
            self.source,
            self._elapsed_ms(started_at),
        )
        if inspect.isawaitable(result):
            await result

    async def _record_failure(self, error_message: str, started_at: float) -> None:
        bounded_message = safe_error_message(error_message, MAX_BINANCE_ERROR_LENGTH)
        log_event(
            self.logger,
            "binance_fetch_failed",
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
