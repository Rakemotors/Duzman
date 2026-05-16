"""Offline tests for the Farside ETF flow HTML collector."""

from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from duzman.collectors.farside import FARSIDE_USER_AGENT, FarsideCollector


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class _HealthRecorder:
    """Capture Farside source-health calls without using a database."""

    def __init__(self) -> None:
        self.successes: list[str] = []
        self.failures: list[tuple[str, str]] = []

    def mark_success(self, source: str) -> None:
        """Record a fake successful source check."""
        self.successes.append(source)

    def mark_failure(self, source: str, error: str) -> None:
        """Record a fake failed source check."""
        self.failures.append((source, error))


@pytest.mark.asyncio
async def test_fetch_etf_flows_parses_btc_fixture_successfully():
    """BTC fixture should normalize provider rows and skip blank cells."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return httpx.Response(200, text=_fixture_text("farside_btc.html"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await FarsideCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_etf_flows(["BTC"])

    assert len(records) == 18
    assert records[0].asset == "BTC"
    assert records[0].provider == "IBIT"
    assert records[0].flow_usd_m == Decimal("123.4")
    assert records[2].provider == "TOTAL"
    assert records[2].flow_usd_m == Decimal("77.8")
    assert observed_requests[0].headers["User-Agent"] == FARSIDE_USER_AGENT
    assert recorder.successes == ["farside"]
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_etf_flows_parses_eth_fixture_successfully():
    """ETH fixture should normalize a separate provider universe."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_fixture_text("farside_eth.html"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await FarsideCollector(client=client).fetch_etf_flows(["ETH"])

    assert len(records) == 14
    assert {record.provider for record in records} == {"ETHA", "FETH", "TOTAL"}
    assert records[0].asset == "ETH"


def test_parse_etf_flows_returns_empty_when_table_is_missing():
    """Missing Farside flow tables should be treated as schema mismatch."""
    records = FarsideCollector().parse_etf_flows("<html><body></body></html>", "BTC")

    assert records == []


def test_parse_etf_flows_returns_empty_when_schema_changes():
    """Unexpected table headers should not raise or persist malformed rows."""
    html = """
    <table>
      <tr><th>Provider</th><th>Value</th></tr>
      <tr><td>IBIT</td><td>123.4</td></tr>
    </table>
    """

    records = FarsideCollector().parse_etf_flows(html, "BTC")

    assert records == []


def test_parse_etf_flows_converts_parentheses_to_negative_decimal():
    """Farside parenthesized values should become negative Decimal values."""
    records = FarsideCollector().parse_etf_flows(_fixture_text("farside_btc.html"), "BTC")

    fbtc_record = next(
        record
        for record in records
        if record.provider == "FBTC" and record.date.isoformat() == "2026-05-16"
    )
    assert fbtc_record.flow_usd_m == Decimal("-45.6")


def test_parse_etf_flows_skips_dash_and_empty_cells():
    """Dash and empty flow cells should not create ETF flow records."""
    records = FarsideCollector().parse_etf_flows(_fixture_text("farside_btc.html"), "BTC")
    may_16_providers = {
        record.provider
        for record in records
        if record.date.isoformat() == "2026-05-16"
    }
    may_14_providers = {
        record.provider
        for record in records
        if record.date.isoformat() == "2026-05-14"
    }

    assert "BITB" not in may_16_providers
    assert "IBIT" not in may_14_providers


@pytest.mark.asyncio
async def test_http_500_records_failure_without_raising():
    """HTTP failures should be recorded and isolated by the collector."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server error")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await FarsideCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_etf_flows(["BTC"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_timeout_records_failure_without_retrying():
    """Timeouts should be bounded source failures without live retries."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await FarsideCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_etf_flows(["BTC"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "timeout" in recorder.failures[0][1]


def _fixture_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")
