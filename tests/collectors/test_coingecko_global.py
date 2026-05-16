"""Offline tests for the CoinGecko Global BTC dominance collector."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from duzman.collectors.coingecko_global import (
    BTC_DOMINANCE_METRIC_NAME,
    COINGECKO_GLOBAL_USER_AGENT,
    CoinGeckoGlobalCollector,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class _HealthRecorder:
    """Capture CoinGecko source-health calls without using a database."""

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
async def test_fetch_btc_dominance_happy_path_normalizes_metric():
    """CoinGecko global response should normalize BTC dominance as Decimal."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return httpx.Response(200, json=_fixture_json())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await CoinGeckoGlobalCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_btc_dominance()

    assert record is not None
    assert record.metric_name == BTC_DOMINANCE_METRIC_NAME
    assert record.value == Decimal("54.32")
    assert record.ts.tzinfo is not None
    assert observed_requests[0].headers["User-Agent"] == COINGECKO_GLOBAL_USER_AGENT
    assert observed_requests[0].url.path == "/api/v3/global"
    assert recorder.successes == ["coingecko"]
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_btc_dominance_http_429_returns_none():
    """HTTP 429 should be recorded as a bounded CoinGecko failure."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_status_response(429))) as client:
        record = await CoinGeckoGlobalCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_btc_dominance()

    assert record is None
    assert "status 429" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_btc_dominance_http_500_returns_none():
    """HTTP 500 should be recorded without raising outward."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(transport=httpx.MockTransport(_status_response(500))) as client:
        record = await CoinGeckoGlobalCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_btc_dominance()

    assert record is None
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_btc_dominance_schema_mismatch_missing_btc_returns_none():
    """Missing btc dominance should be treated as schema mismatch."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": {"market_cap_percentage": {"eth": 12.4}}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await CoinGeckoGlobalCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_btc_dominance()

    assert record is None
    assert "missing btc" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_btc_dominance_invalid_json_returns_none():
    """Invalid JSON should be recorded as a controlled collector failure."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await CoinGeckoGlobalCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_btc_dominance()

    assert record is None
    assert recorder.successes == []
    assert len(recorder.failures) == 1


def _fixture_json() -> dict[str, object]:
    return json.loads((FIXTURE_DIR / "coingecko_global.json").read_text(encoding="utf-8"))


def _status_response(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={})

    return handler
