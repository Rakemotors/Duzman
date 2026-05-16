"""Offline tests for the OKX public derivatives collector."""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from duzman.collectors.okx import OKXCollector, OKX_RATIO_TYPE_GLOBAL_ACCOUNTS


class _HealthRecorder:
    """Capture source-health writes without using a database."""

    def __init__(self) -> None:
        self.successes: list[tuple[str, int]] = []
        self.failures: list[tuple[str, str, int | None]] = []

    def record_success(self, source: str, latency_ms: int) -> None:
        """Record a fake successful source-health event."""
        self.successes.append((source, latency_ms))

    def record_failure(
        self,
        source: str,
        error_message: str,
        latency_ms: int | None = None,
    ) -> None:
        """Record a fake failed source-health event."""
        self.failures.append((source, error_message, latency_ms))


@pytest.mark.asyncio
async def test_fetch_funding_rates_happy_path_normalizes_fields():
    """Funding fetch should normalize OKX funding fractions into percents."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        assert "OK-ACCESS-KEY" not in request.headers
        assert "OK-ACCESS-SIGN" not in request.headers
        return httpx.Response(200, json=_funding_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

    assert len(records) == 1
    assert records[0].asset == "BTC"
    assert records[0].exchange == "okx"
    assert records[0].funding_rate_pct == Decimal("0.01")
    assert records[0].next_funding_time == datetime.fromtimestamp(
        1715775420000 / 1000,
        tz=timezone.utc,
    )
    assert observed_requests[0].url.path == "/api/v5/public/funding-rate"
    assert observed_requests[0].url.params["instId"] == "BTC-USDT-SWAP"
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_open_interest_happy_path_computes_usd_value():
    """Open interest fetch should multiply contracts by OKX mark price."""
    recorder = _HealthRecorder()
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        if request.url.path == "/api/v5/public/mark-price":
            return httpx.Response(200, json=_okx_payload({"markPx": "100.25"}))
        return httpx.Response(
            200,
            json=_okx_payload({"oi": "2.5", "oiCcy": "ETH"}),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_open_interest(["ETH"])

    assert observed_paths == [
        "/api/v5/public/mark-price",
        "/api/v5/public/open-interest",
    ]
    assert len(records) == 1
    assert records[0].asset == "ETH"
    assert records[0].exchange == "okx"
    assert records[0].oi_contracts == Decimal("2.5")
    assert records[0].oi_usd == Decimal("250.625")
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_long_short_ratio_happy_path_normalizes_percentages():
    """Long/short fetch should derive percentages from OKX ratio pairs."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_okx_payload(["1715775420000", "1.5"]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_long_short_ratio(["SOL"])

    assert len(records) == 1
    assert records[0].asset == "SOL"
    assert records[0].exchange == "okx"
    assert records[0].ratio_type == OKX_RATIO_TYPE_GLOBAL_ACCOUNTS
    assert records[0].long_pct == 60.0
    assert records[0].short_pct == 40.0
    assert records[0].ratio == 1.5
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_funding_rates_okx_code_failure_returns_empty_list():
    """OKX code failures should be recorded and not escape funding fetch."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_okx_code_failure)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "code=50001" in recorder.failures[0][1]
    assert "bad request" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_open_interest_okx_code_failure_returns_empty_list():
    """OKX code failures should be isolated for open interest fetches."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_okx_code_failure)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_open_interest(["ETH"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "code=50001" in recorder.failures[0][1]
    assert "bad request" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_long_short_ratio_okx_code_failure_returns_empty_list():
    """OKX code failures should be isolated for long/short ratio fetches."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_okx_code_failure)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_long_short_ratio(["SOL"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "code=50001" in recorder.failures[0][1]
    assert "bad request" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_funding_rates_http_500_returns_empty_list():
    """HTTP 500 should be recorded as source failure without raising outward."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": "0", "data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_open_interest_timeout_returns_empty_list():
    """Timeout should be recorded as source failure without retrying."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_open_interest(["ETH"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "timed out" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_long_short_ratio_http_500_returns_empty_list():
    """Long/short HTTP errors should be recorded and bounded."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"code": "0", "data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_long_short_ratio(["SOL"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_empty_data_array_returns_empty_list_without_crashing():
    """Empty OKX data arrays should be handled as missing data."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "0", "msg": "", "data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "empty" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_all_stage_a_symbols_are_supported_without_private_endpoints():
    """All configured Stage A assets should map to OKX public funding endpoints."""
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        return httpx.Response(200, json=_funding_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await OKXCollector(client=client).fetch_funding_rates(
            ["BTC", "ETH", "SOL", "SUI", "TON", "UNI"]
        )

    assert len(records) == 6
    assert set(observed_paths) == {"/api/v5/public/funding-rate"}
    assert all("account" not in path and "trade" not in path and "asset" not in path for path in observed_paths)


def _funding_payload() -> dict[str, object]:
    return _okx_payload(
        {
            "fundingRate": "0.0001",
            "nextFundingTime": "1715775420000",
        }
    )


def _okx_payload(item: dict[str, str] | list[str]) -> dict[str, object]:
    return {"code": "0", "msg": "", "data": [item]}


def _okx_code_failure(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"code": "50001", "msg": "bad request", "data": []},
    )
