"""Offline tests for the Alternative.me Fear & Greed collector."""

import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from duzman.collectors.alternative_me import (
    ALTERNATIVE_ME_USER_AGENT,
    FEAR_GREED_METRIC_NAME,
    AlternativeMeCollector,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures"


class _HealthRecorder:
    """Capture Alternative.me source-health calls without using a database."""

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
async def test_fetch_fear_greed_happy_path_normalizes_metric():
    """Alternative.me response should normalize Fear & Greed as Decimal."""
    recorder = _HealthRecorder()
    observed_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return httpx.Response(200, json=_fixture_json())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await AlternativeMeCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_fear_greed()

    assert record is not None
    assert record.metric_name == FEAR_GREED_METRIC_NAME
    assert record.value == Decimal("42")
    assert record.ts.tzinfo is not None
    assert observed_requests[0].headers["User-Agent"] == ALTERNATIVE_ME_USER_AGENT
    assert observed_requests[0].url.path == "/fng/"
    assert observed_requests[0].url.params["limit"] == "1"
    assert recorder.successes == ["alternative_me"]
    assert recorder.failures == []


@pytest.mark.asyncio
async def test_fetch_fear_greed_http_429_returns_none():
    """HTTP 429 should be recorded as a bounded Alternative.me failure."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_status_response(429))
    ) as client:
        record = await AlternativeMeCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_fear_greed()

    assert record is None
    assert "status 429" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_fear_greed_http_500_returns_none():
    """HTTP 500 should be recorded without raising outward."""
    recorder = _HealthRecorder()

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(_status_response(500))
    ) as client:
        record = await AlternativeMeCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_fear_greed()

    assert record is None
    assert "status 500" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_fear_greed_empty_data_returns_none():
    """Empty data arrays should be treated as schema mismatch."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await AlternativeMeCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_fear_greed()

    assert record is None
    assert "empty data" in recorder.failures[0][1]


@pytest.mark.asyncio
async def test_fetch_fear_greed_invalid_json_returns_none():
    """Invalid JSON should be recorded as a controlled collector failure."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await AlternativeMeCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_fear_greed()

    assert record is None
    assert recorder.successes == []
    assert len(recorder.failures) == 1


@pytest.mark.asyncio
async def test_fetch_fear_greed_invalid_decimal_returns_none():
    """Non-numeric Fear & Greed values should not escape the collector."""
    recorder = _HealthRecorder()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"value": "not-a-number"}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        record = await AlternativeMeCollector(
            client=client,
            health_recorder=recorder,
        ).fetch_fear_greed()

    assert record is None
    assert "invalid fear greed value" in recorder.failures[0][1]


def _fixture_json() -> dict[str, object]:
    return json.loads((FIXTURE_DIR / "alternative_me_fng.json").read_text(encoding="utf-8"))


def _status_response(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={})

    return handler
