"""Farside Investors HTML collector for public BTC/ETH ETF flows."""

from __future__ import annotations

import inspect
import logging
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Protocol

import httpx
from bs4 import BeautifulSoup
from bs4.element import Tag

from duzman.collectors.records import ETFFlowRecord
from duzman.logging_config import get_logger, log_event, safe_error_message


FARSIDE_SOURCE = "farside"
FARSIDE_BASE_URLS: dict[str, str] = {
    "BTC": "https://farside.co.uk/btc/",
    "ETH": "https://farside.co.uk/eth/",
}
FARSIDE_USER_AGENT = "Duzman/0.1 (+contact@example.com)"
MAX_FARSIDE_ERROR_LENGTH = 200
MAX_FARSIDE_FLOW_DAYS = 30
MAX_FARSIDE_COLUMN_DRIFT = 2


class FarsideSourceHealthRecorder(Protocol):
    """Minimal source-health recorder interface used by FarsideCollector."""

    def mark_success(self, source: str) -> object:
        """Record a successful public source check."""

    def mark_failure(self, source: str, error: str) -> object:
        """Record a failed public source check with a bounded error message."""


class FarsideCollectorError(Exception):
    """Controlled error for one Farside HTML request or parse attempt."""


class FarsideCollector:
    """Fetch and normalize public Farside BTC/ETH ETF flow tables."""

    source = FARSIDE_SOURCE
    supported_assets = frozenset(FARSIDE_BASE_URLS)

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        health_recorder: FarsideSourceHealthRecorder | None = None,
    ) -> None:
        self.client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": FARSIDE_USER_AGENT},
        )
        self.timeout_seconds = timeout_seconds
        self.health_recorder = health_recorder
        self.logger = get_logger(__name__)

    async def fetch_etf_flows(self, assets: Sequence[str]) -> list[ETFFlowRecord]:
        """Fetch public ETF flow records for enabled BTC/ETH assets."""
        records: list[ETFFlowRecord] = []
        for asset in assets:
            records.extend(await self._fetch_asset_etf_flows(asset))
        return records

    async def _fetch_asset_etf_flows(self, asset: str) -> list[ETFFlowRecord]:
        started_at = monotonic()
        normalized_asset = asset.upper()
        log_event(self.logger, "farside_fetch_start", asset=normalized_asset)
        try:
            url = self._url_for_asset(normalized_asset)
            response = await self.client.get(
                url,
                timeout=self.timeout_seconds,
                headers={"User-Agent": FARSIDE_USER_AGENT},
            )
            if not 200 <= response.status_code < 300:
                raise FarsideCollectorError(
                    f"Farside request returned status {response.status_code}"
                )
            records = self.parse_etf_flows(response.text, normalized_asset)
        except Exception as exc:
            bounded_message = safe_error_message(exc, MAX_FARSIDE_ERROR_LENGTH)
            log_event(
                self.logger,
                "farside_parse_error",
                level=logging.ERROR,
                asset=normalized_asset,
                safe_error_message=bounded_message,
            )
            await self._record_failure(bounded_message)
            return []

        await self._record_success()
        log_event(
            self.logger,
            "farside_fetch_success",
            asset=normalized_asset,
            record_count=len(records),
            latency_ms=self._elapsed_ms(started_at),
        )
        return records

    def parse_etf_flows(self, html: str, asset: str) -> list[ETFFlowRecord]:
        """Parse Farside HTML into normalized ETF flow records."""
        soup = BeautifulSoup(html, "lxml")
        table = self._find_flow_table(soup)
        if table is None:
            self._log_schema_mismatch(asset, [])
            return []

        headers = self._table_headers(table)
        if not self._headers_are_valid(headers):
            self._log_schema_mismatch(asset, headers)
            return []

        records: list[ETFFlowRecord] = []
        expected_column_count = len(headers)
        provider_headers = headers[1:]
        for row in table.find_all("tr"):
            cells = self._row_cells(row)
            if not cells or cells == headers:
                continue
            if abs(len(cells) - expected_column_count) > MAX_FARSIDE_COLUMN_DRIFT:
                self._log_schema_mismatch(asset, headers)
                return []
            records.extend(self._records_from_cells(asset, provider_headers, cells))
            if len({record.date for record in records}) >= MAX_FARSIDE_FLOW_DAYS:
                break
        return records

    def _records_from_cells(
        self,
        asset: str,
        provider_headers: Sequence[str],
        cells: Sequence[str],
    ) -> list[ETFFlowRecord]:
        flow_date = self._parse_date(cells[0])
        records: list[ETFFlowRecord] = []
        for provider, raw_value in zip(provider_headers, cells[1:], strict=False):
            flow_value = self._parse_flow_value(raw_value)
            if flow_value is None:
                continue
            records.append(
                ETFFlowRecord(
                    date=flow_date,
                    asset=asset,
                    provider=self._normalize_provider(provider),
                    flow_usd_m=flow_value,
                )
            )
        return records

    def _find_flow_table(self, soup: BeautifulSoup) -> Tag | None:
        for table in soup.find_all("table"):
            headers = self._table_headers(table)
            if self._headers_are_valid(headers):
                return table
        return None

    def _headers_are_valid(self, headers: Sequence[str]) -> bool:
        normalized_headers = [header.lower() for header in headers]
        return (
            len(headers) >= 3
            and normalized_headers[0] in {"date", "day"}
            and "total" in normalized_headers
        )

    def _table_headers(self, table: Tag) -> list[str]:
        header_row = table.find("tr")
        if header_row is None:
            return []
        headers = [
            self._cell_text(cell)
            for cell in header_row.find_all(["th", "td"])
            if self._cell_text(cell)
        ]
        return headers

    def _row_cells(self, row: Tag) -> list[str]:
        return [
            self._cell_text(cell)
            for cell in row.find_all(["td", "th"])
        ]

    def _cell_text(self, cell: Tag) -> str:
        return " ".join(cell.get_text(" ", strip=True).split())

    def _parse_date(self, raw_value: str) -> date:
        for date_format in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(raw_value, date_format).date()
            except ValueError:
                continue
        raise FarsideCollectorError(f"Farside row has invalid date: {raw_value}")

    def _parse_flow_value(self, raw_value: str) -> Decimal | None:
        normalized_value = raw_value.strip().replace(",", "")
        if normalized_value in {"", "-"}:
            return None
        if normalized_value.startswith("(") and normalized_value.endswith(")"):
            normalized_value = f"-{normalized_value[1:-1]}"
        try:
            return Decimal(normalized_value)
        except InvalidOperation as exc:
            raise FarsideCollectorError("Farside row has invalid flow value") from exc

    def _normalize_provider(self, provider: str) -> str:
        if provider.strip().lower() == "total":
            return "TOTAL"
        return provider.strip().upper()

    def _url_for_asset(self, asset: str) -> str:
        try:
            return FARSIDE_BASE_URLS[asset]
        except KeyError as exc:
            raise FarsideCollectorError(
                f"Farside ETF flows are not supported for asset: {asset}"
            ) from exc

    def _log_schema_mismatch(self, asset: str, columns: Sequence[str]) -> None:
        log_event(
            self.logger,
            "farside_schema_mismatch",
            level=logging.WARNING,
            asset=asset,
            columns=list(columns),
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
        result = self.health_recorder.mark_failure(self.source, error_message)
        if inspect.isawaitable(result):
            await result

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
