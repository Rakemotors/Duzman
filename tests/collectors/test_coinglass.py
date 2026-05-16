"""Offline tests for the CoinGlass public liquidations collector."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from duzman.collectors.coinglass import CoinGlassCollector


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class _HealthRecorder:
    """Capture CoinGlass source-health calls without using a database."""

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
async def test_fetch_liquidations_1h_happy_path_normalizes_fields():
    """Liquidation history should normalize latest 1h and rolling 24h values."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        assert request.headers["CG-API-KEY"] == "fake-key"
        return httpx.Response(200, json=_fixture_json("coinglass_liquidations_btc.json"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await CoinGlassCollector(
            client=client,
            api_key="fake-key",
            health_recorder=recorder,
        ).fetch_liquidations_1h("BTC")

    assert record is not None
    assert record.asset == "BTC"
    assert record.longs_1h_usd == Decimal("200.50")
    assert record.shorts_1h_usd == Decimal("75.25")
    assert record.longs_24h_usd == Decimal("300.75")
    assert record.shorts_24h_usd == Decimal("126.00")
    assert observed_requests[0].url.path == "/api/futures/liquidation/v2/history"
    assert observed_requests[0].url.params["interval"] == "1h"
    assert recorder.successes == ["coinglass"]
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_heatmap_happy_path_buckets_current_price_range():
    """Heatmap fetch should return twenty 1 percent buckets around current price."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_fixture_json("coinglass_heatmap_btc_24h.json"))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        records = await CoinGlassCollector(
            client=client,
            api_key="fake-key",
            health_recorder=recorder,
            current_price_provider=lambda asset: Decimal("100000"),
        ).fetch_heatmap("BTC", "24h")

    assert len(records) == 20
    assert records[0].asset == "BTC"
    assert records[0].timeframe == "24h"
    assert records[0].price_low == Decimal("90000.00")
    assert records[0].liquidation_volume_usd == Decimal("1000.50")
    assert records[10].liquidation_volume_usd == Decimal("250.25")
    assert recorder.successes == ["coinglass"]
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_missing_api_key_gracefully_skips_without_request():
    """Missing CoinGlass API key should record failure and skip HTTP."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("missing API key must not call CoinGlass")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await CoinGlassCollector(
            client=client,
            api_key="",
            health_recorder=recorder,
        ).fetch_liquidations_1h("BTC")

    assert record is None
    assert recorder.successes == []
    assert len(recorder.failures) == 1
    assert "API key" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_http_429_returns_none_and_records_failure():
    """HTTP 429 should be isolated as a bounded CoinGlass failure."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_status_response(429))
    ) as client:
        record = await CoinGlassCollector(
            client=client,
            api_key="fake-key",
            health_recorder=recorder,
        ).fetch_liquidations_1h("BTC")

    assert record is None
    assert "status 429" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_http_500_returns_empty_heatmap_and_records_failure():
    """HTTP 500 should return an empty heatmap without raising outward."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_status_response(500))
    ) as client:
        records = await CoinGlassCollector(
            client=client,
            api_key="fake-key",
            health_recorder=recorder,
            current_price_provider=lambda asset: Decimal("100000"),
        ).fetch_heatmap("BTC", "24h")

    assert records == []
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_schema_mismatch_code_failure_returns_none():
    """CoinGlass code failures should be treated as schema mismatch."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "1001", "msg": "bad", "data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await CoinGlassCollector(
            client=client,
            api_key="fake-key",
            health_recorder=recorder,
        ).fetch_liquidations_1h("BTC")

    assert record is None
    assert "code=1001" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_empty_json_response_returns_none():
    """Non-object CoinGlass JSON should not escape the collector."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await CoinGlassCollector(
            client=client,
            api_key="fake-key",
            health_recorder=recorder,
        ).fetch_liquidations_1h("BTC")

    assert record is None
    assert "JSON object" in recorder.failures[0][1]


def _fixture_json(name: str) -> dict[str, object]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _status_response(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"code": "0", "data": []})

    return handler
