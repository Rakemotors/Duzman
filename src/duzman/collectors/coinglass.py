"""CoinGlass public derivatives collector for liquidations and heatmaps."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any, Literal, Protocol

import httpx
from pydantic import SecretStr

from duzman.collectors.records import HeatmapBucketRecord, LiquidationRecord
from duzman.logging_config import get_logger, log_event, safe_error_message
from duzman.settings import settings


COINGLASS_SOURCE = "coinglass"
MAX_COINGLASS_ERROR_LENGTH = 200
COINGLASS_INTERVAL_1H = "1h"
COINGLASS_HEATMAP_TIMEFRAMES = ("24h", "7d")
HEATMAP_BUCKET_STEP_PCT = Decimal("0.01")
HEATMAP_BUCKET_RANGE_PCT = Decimal("0.10")


class CoinGlassSourceHealthRecorder(Protocol):
    """Minimal source-health recorder interface used by CoinGlassCollector."""

    def mark_success(self, source: str) -> object:
        """Record a successful public source check."""

    def mark_failure(self, source: str, error: str) -> object:
        """Record a failed public source check with a bounded error message."""


class CoinGlassCollectorError(Exception):
    """Controlled error for one CoinGlass public request attempt."""


class CoinGlassCollector:
    """Fetch public CoinGlass liquidation and simplified heatmap metrics."""

    source = COINGLASS_SOURCE
    base_url = "https://open-api-v3.coinglass.com"
    supported_symbols: tuple[str, ...] = ("BTC", "ETH", "SOL", "SUI", "TON", "UNI")

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        api_key: SecretStr | str | None = None,
        health_recorder: CoinGlassSourceHealthRecorder | None = None,
        current_price_provider: Callable[[str], Decimal | None] | None = None,
        request_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key if api_key is not None else settings.coinglass_api_key
        self.health_recorder = health_recorder
        self.current_price_provider = current_price_provider
        self.request_semaphore = request_semaphore or asyncio.Semaphore(2)
        self.logger = get_logger(__name__)
        self._missing_key_reported = False

    async def fetch_liquidations_1h(self, symbol: str) -> LiquidationRecord | None:
        """Fetch the latest hourly liquidation totals for one Stage A asset."""
        if not await self._ensure_api_key():
            return None
        started_at = monotonic()
        asset = self._normalize_symbol(symbol)
        try:
            payload = await self._get_json(
                "/api/futures/liquidation/v2/history",
                {"symbol": asset, "interval": COINGLASS_INTERVAL_1H},
            )
            items = self._data_items(payload, endpoint="liquidations", asset=asset)
            if not items:
                raise CoinGlassCollectorError("CoinGlass liquidation data was empty")
            record = self._liquidation_record_from_items(asset, items)
        except Exception as exc:
            await self._record_failure(safe_error_message(exc, MAX_COINGLASS_ERROR_LENGTH))
            log_event(
                self.logger,
                "coinglass_schema_mismatch",
                level=logging.ERROR,
                endpoint="liquidations",
                asset=asset,
            )
            return None

        await self._record_success()
        log_event(
            self.logger,
            "coinglass_liquidations_fetch_success",
            asset=asset,
            latency_ms=self._elapsed_ms(started_at),
        )
        return record

    async def fetch_heatmap(
        self,
        symbol: str,
        timeframe: Literal["24h", "7d"],
    ) -> list[HeatmapBucketRecord]:
        """Fetch and bucket the CoinGlass liquidation heatmap for one asset."""
        if timeframe not in COINGLASS_HEATMAP_TIMEFRAMES:
            raise CoinGlassCollectorError(
                f"Unsupported CoinGlass heatmap timeframe: {timeframe}"
            )
        if not await self._ensure_api_key():
            return []
        started_at = monotonic()
        asset = self._normalize_symbol(symbol)
        current_price = self._current_price(asset)
        if current_price is None:
            log_event(self.logger, "coinglass_heatmap_no_price", asset=asset)
            return []
        try:
            payload = await self._get_json(
                "/api/futures/liquidation/v2/heatmap/model1",
                {"symbol": asset, "interval": timeframe},
            )
            items = self._data_items(payload, endpoint="heatmap", asset=asset)
            records = self._heatmap_records_from_items(
                asset=asset,
                timeframe=timeframe,
                current_price=current_price,
                items=items,
            )
        except Exception as exc:
            await self._record_failure(safe_error_message(exc, MAX_COINGLASS_ERROR_LENGTH))
            log_event(
                self.logger,
                "coinglass_schema_mismatch",
                level=logging.ERROR,
                endpoint="heatmap",
                asset=asset,
            )
            return []

        await self._record_success()
        log_event(
            self.logger,
            "coinglass_heatmap_fetch_success",
            asset=asset,
            timeframe=timeframe,
            bucket_count=len(records),
            latency_ms=self._elapsed_ms(started_at),
        )
        return records

    async def _ensure_api_key(self) -> bool:
        if self._api_key_value():
            return True
        if not self._missing_key_reported:
            log_event(self.logger, "coinglass_no_api_key", level=logging.WARNING)
            self._missing_key_reported = True
        await self._record_failure("CoinGlass API key is not configured")
        return False

    async def _get_json(
        self,
        path: str,
        params: Mapping[str, str],
    ) -> Mapping[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with self.request_semaphore:
                response = await self.client.get(
                    url,
                    params=dict(params),
                    headers={"CG-API-KEY": self._api_key_value() or ""},
                    timeout=self.timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise CoinGlassCollectorError("CoinGlass public request timed out") from exc
        except httpx.HTTPError as exc:
            raise CoinGlassCollectorError("CoinGlass public request failed") from exc

        if not 200 <= response.status_code < 300:
            raise CoinGlassCollectorError(
                f"CoinGlass public request returned status {response.status_code}"
            )
        payload = response.json()
        if not isinstance(payload, Mapping):
            raise CoinGlassCollectorError("CoinGlass response must be a JSON object")
        code = str(payload.get("code"))
        if code != "0":
            raise CoinGlassCollectorError(f"CoinGlass code={code}")
        return payload

    def _data_items(
        self,
        payload: Mapping[str, Any],
        endpoint: str,
        asset: str,
    ) -> list[Mapping[str, Any]]:
        data = payload.get("data")
        if not isinstance(data, list):
            log_event(
                self.logger,
                "coinglass_schema_mismatch",
                endpoint=endpoint,
                asset=asset,
            )
            raise CoinGlassCollectorError("CoinGlass response is missing data array")
        items = [item for item in data if isinstance(item, Mapping)]
        if len(items) != len(data):
            raise CoinGlassCollectorError("CoinGlass data array contains invalid items")
        return items

    def _liquidation_record_from_items(
        self,
        asset: str,
        items: Sequence[Mapping[str, Any]],
    ) -> LiquidationRecord:
        latest_item = items[-1]
        long_values = [
            self._decimal_from_aliases(
                item,
                ("longLiquidationUsd", "longsUsd", "longUsd"),
            )
            for item in items
        ]
        short_values = [
            self._decimal_from_aliases(
                item,
                ("shortLiquidationUsd", "shortsUsd", "shortUsd"),
            )
            for item in items
        ]
        return LiquidationRecord(
            ts=self._timestamp_from_item(latest_item),
            asset=asset,
            longs_1h_usd=long_values[-1],
            shorts_1h_usd=short_values[-1],
            longs_24h_usd=sum(long_values[-24:], Decimal("0")),
            shorts_24h_usd=sum(short_values[-24:], Decimal("0")),
        )

    def _heatmap_records_from_items(
        self,
        asset: str,
        timeframe: Literal["24h", "7d"],
        current_price: Decimal,
        items: Sequence[Mapping[str, Any]],
    ) -> list[HeatmapBucketRecord]:
        now = datetime.now(timezone.utc)
        buckets = self._empty_heatmap_buckets(asset, timeframe, current_price, now)
        lower_bound = current_price * (Decimal("1") - HEATMAP_BUCKET_RANGE_PCT)
        upper_bound = current_price * (Decimal("1") + HEATMAP_BUCKET_RANGE_PCT)
        step = current_price * HEATMAP_BUCKET_STEP_PCT
        for item in items:
            price = self._decimal_from_aliases(item, ("price", "priceLevel", "p"))
            if price < lower_bound or price >= upper_bound:
                continue
            bucket_index = int((price - lower_bound) / step)
            volume = self._decimal_from_aliases(
                item,
                ("liquidationVolumeUsd", "volumeUsd", "v"),
            )
            existing = buckets[bucket_index]
            buckets[bucket_index] = HeatmapBucketRecord(
                ts=existing.ts,
                asset=existing.asset,
                timeframe=existing.timeframe,
                price_low=existing.price_low,
                price_high=existing.price_high,
                liquidation_volume_usd=existing.liquidation_volume_usd + volume,
            )
        return buckets

    def _empty_heatmap_buckets(
        self,
        asset: str,
        timeframe: str,
        current_price: Decimal,
        ts: datetime,
    ) -> list[HeatmapBucketRecord]:
        lower_bound = current_price * (Decimal("1") - HEATMAP_BUCKET_RANGE_PCT)
        step = current_price * HEATMAP_BUCKET_STEP_PCT
        return [
            HeatmapBucketRecord(
                ts=ts,
                asset=asset,
                timeframe=timeframe,
                price_low=lower_bound + (step * Decimal(index)),
                price_high=lower_bound + (step * Decimal(index + 1)),
                liquidation_volume_usd=Decimal("0"),
            )
            for index in range(20)
        ]

    def _current_price(self, asset: str) -> Decimal | None:
        if self.current_price_provider is None:
            return None
        return self.current_price_provider(asset)

    def _normalize_symbol(self, symbol: str) -> str:
        asset = symbol.upper()
        if asset not in self.supported_symbols:
            raise CoinGlassCollectorError(f"CoinGlass asset is not supported: {symbol}")
        return asset

    def _decimal_from_aliases(
        self,
        item: Mapping[str, Any],
        aliases: Sequence[str],
    ) -> Decimal:
        for alias in aliases:
            if alias in item and item[alias] not in (None, ""):
                try:
                    return Decimal(str(item[alias]))
                except (InvalidOperation, ValueError) as exc:
                    raise CoinGlassCollectorError(
                        f"CoinGlass field has invalid decimal value: {alias}"
                    ) from exc
        raise CoinGlassCollectorError(
            f"CoinGlass data item is missing field: {aliases[0]}"
        )

    def _timestamp_from_item(self, item: Mapping[str, Any]) -> datetime:
        for alias in ("time", "timestamp", "ts"):
            if alias in item and item[alias] not in (None, ""):
                value = int(str(item[alias]))
                if value > 10_000_000_000:
                    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
                return datetime.fromtimestamp(value, tz=timezone.utc)
        return datetime.now(timezone.utc)

    def _api_key_value(self) -> str | None:
        if isinstance(self.api_key, SecretStr):
            return self.api_key.get_secret_value()
        return self.api_key

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
            safe_error_message(error_message, MAX_COINGLASS_ERROR_LENGTH),
        )
        if inspect.isawaitable(result):
            await result

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
