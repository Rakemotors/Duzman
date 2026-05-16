"""Offline tests for the Bybit public derivatives collector."""

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from duzman.collectors.bybit import (
    BYBIT_RATIO_TYPE_GLOBAL_ACCOUNTS,
    BybitCollector,
)


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
    """Funding fetch should normalize Bybit ticker fields without auth headers."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        assert "X-BAPI-API-KEY" not in request.headers
        return httpx.Response(200, json=_ticker_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

    assert len(records) == 1
    assert records[0].asset == "BTC"
    assert records[0].exchange == "bybit"
    assert records[0].funding_rate_pct == Decimal("0.01")
    assert records[0].next_funding_time == datetime.fromtimestamp(1715775420000 / 1000, tz=timezone.utc)
    assert observed_requests[0].url.path == "/v5/market/tickers"
    assert observed_requests[0].url.params["category"] == "linear"
    assert observed_requests[0].url.params["symbol"] == "BTCUSDT"
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_open_interest_happy_path_computes_usd_value():
    """Open interest fetch should multiply contracts by mark price."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v5/market/tickers":
            return httpx.Response(200, json=_ticker_payload(mark_price="100.25"))
        return httpx.Response(
            200,
            json=_wrapped_payload({"openInterest": "2.5"}),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_open_interest(["ETH"])

    assert len(records) == 1
    assert records[0].asset == "ETH"
    assert records[0].exchange == "bybit"
    assert records[0].oi_contracts == Decimal("2.5")
    assert records[0].oi_usd == Decimal("250.625")
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_long_short_ratio_happy_path_normalizes_percentages():
    """Long/short fetch should normalize global account ratios."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=_wrapped_payload({"buyRatio": "0.60", "sellRatio": "0.40"}),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_long_short_ratio(["SOL"])

    assert len(records) == 1
    assert records[0].asset == "SOL"
    assert records[0].exchange == "bybit"
    assert records[0].ratio_type == BYBIT_RATIO_TYPE_GLOBAL_ACCOUNTS
    assert records[0].long_pct == 60.0
    assert records[0].short_pct == 40.0
    assert records[0].ratio == 1.5
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_mark_prices_happy_path_normalizes_mark_price():
    """Mark-price fetch should return asset and Decimal mark price."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ticker_payload(mark_price="67123.45"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_mark_prices(["BTC"])

    assert records == [{"asset": "BTC", "mark_price": Decimal("67123.45")}]
    assert len(recorder.successes) == 1
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_mark_prices_retcode_failure_returns_empty_list():
    """Mark-price retCode failures should be recorded and isolated."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_retcode_failure)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_mark_prices(["BTC"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "retCode=10001" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_mark_prices_http_500_returns_empty_list():
    """Mark-price HTTP errors should be recorded without raising outward."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"retCode": 0})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_mark_prices(["BTC"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_funding_rates_retcode_failure_returns_empty_list():
    """Bybit retCode failures should be recorded and not escape the collector."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_retcode_failure)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "retCode=10001" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_open_interest_retcode_failure_returns_empty_list():
    """Open interest retCode failures should be isolated per symbol."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_retcode_failure)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_open_interest(["ETH"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "retCode=10001" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_long_short_ratio_retcode_failure_returns_empty_list():
    """Long/short retCode failures should be isolated per symbol."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_retcode_failure)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_long_short_ratio(["SOL"])

    assert records == []
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "retCode=10001" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_funding_rates_http_500_returns_empty_list():
    """HTTP 500 should be recorded as source failure without raising outward."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"retCode": 0})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

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
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_open_interest(["ETH"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "timed out" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_long_short_ratio_http_500_returns_empty_list():
    """Long/short HTTP errors should be recorded and bounded."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"retCode": 0})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_long_short_ratio(["SOL"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_empty_result_list_returns_empty_list_without_crashing():
    """Empty Bybit result lists should be handled as missing data."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"retCode": 0, "retMsg": "OK", "result": {"list": []}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client, health_recorder=recorder).fetch_funding_rates(["BTC"])

    assert records == []
    assert len(recorder.failures) == 1
    assert "empty" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_all_stage_a_symbols_are_supported_without_private_endpoints():
    """All configured Stage A assets should map to Bybit linear public symbols."""
    observed_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_paths.append(request.url.path)
        return httpx.Response(200, json=_ticker_payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await BybitCollector(client=client).fetch_funding_rates(["BTC", "ETH", "SOL", "SUI", "TON", "UNI"])

    assert len(records) == 6
    assert set(observed_paths) == {"/v5/market/tickers"}
    assert all("order" not in path and "account" not in path for path in observed_paths)


def _ticker_payload(mark_price: str = "67000.5") -> dict[str, object]:
    return _wrapped_payload(
        {
            "fundingRate": "0.0001",
            "nextFundingTime": "1715775420000",
            "markPrice": mark_price,
        }
    )


def _wrapped_payload(item: dict[str, str]) -> dict[str, object]:
    return {"retCode": 0, "retMsg": "OK", "result": {"list": [item]}}


def _retcode_failure(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={"retCode": 10001, "retMsg": "bad request", "result": {"list": []}},
    )
