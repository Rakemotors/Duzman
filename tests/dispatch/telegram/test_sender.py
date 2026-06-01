# tests/dispatch/telegram/test_sender.py
# Telegram base sender tests. Exercises retry and result behavior with fake
# transports only and no real Telegram API calls.
"""Tests for TelegramBaseSender."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
import pytest

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.telegram.client import HttpResponse, TelegramHttpClient
from duzman.dispatch.telegram.result import (
    TELEGRAM_ERROR_API,
    TELEGRAM_ERROR_NETWORK,
    TELEGRAM_ERROR_RATE_LIMITED_EXHAUSTED,
    TELEGRAM_ERROR_TIMEOUT,
    TELEGRAM_STATUS_FAILED,
    TELEGRAM_STATUS_SENT,
    TELEGRAM_STATUS_SKIPPED_DISABLED,
)
from duzman.dispatch.telegram.sender import TelegramBaseSender

FAKE_TOKEN = "test-bot-token-do-not-use"
FAKE_CHAT_ID = "test-chat-id-12345"
NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class FakeResponse:
    """Small response object implementing the client response protocol."""

    status_code: int
    body: object
    headers: Mapping[str, str] = field(default_factory=dict)

    def json(self) -> object:
        """Return the fake JSON body."""
        return self.body


class FakeHttpTransport:
    """Fake HTTP transport with queued outcomes."""

    def __init__(self, outcomes: list[HttpResponse | BaseException]) -> None:
        self.outcomes = outcomes
        self.calls: list[dict[str, object]] = []

    async def post(
        self,
        *,
        url: str,
        json: Mapping[str, object],
        request_timeout: float,
    ) -> HttpResponse:
        """Record the request and return or raise the next queued outcome."""
        self.calls.append({"url": url, "json": dict(json), "timeout": request_timeout})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.mark.asyncio
async def test_sender_success_attempts_one() -> None:
    """A successful first send should return sent with one attempt."""
    transport = FakeHttpTransport(
        [FakeResponse(200, {"ok": True, "result": {"message_id": 321}})]
    )
    sender = _sender(transport)

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_SENT
    assert result.telegram_message_id == 321
    assert result.error_reason is None
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_sender_transient_failure_then_success_attempts_two() -> None:
    """A transient transport failure should be retried once."""
    transport = FakeHttpTransport(
        [
            httpx.ConnectError("temporary network issue"),
            FakeResponse(200, {"ok": True, "result": {"message_id": 322}}),
        ]
    )
    sender = _sender(transport)

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_SENT
    assert result.telegram_message_id == 322
    assert result.attempts == 2
    assert len(transport.calls) == 2


@pytest.mark.asyncio
async def test_sender_transient_failure_twice_returns_failed() -> None:
    """Exhausting transient retry budget should return failed."""
    transport = FakeHttpTransport(
        [
            httpx.ConnectError("temporary network issue"),
            httpx.ConnectError("temporary network issue"),
        ]
    )
    sender = _sender(transport)

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_FAILED
    assert result.telegram_message_id is None
    assert result.error_reason == TELEGRAM_ERROR_NETWORK
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_sender_timeout_failure_twice_returns_failed() -> None:
    """Exhausting timeout retry budget should return failed."""
    transport = FakeHttpTransport(
        [
            httpx.TimeoutException("temporary timeout"),
            httpx.TimeoutException("temporary timeout"),
        ]
    )
    sender = _sender(transport)

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_FAILED
    assert result.error_reason == TELEGRAM_ERROR_TIMEOUT
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_sender_permanent_error_attempts_one() -> None:
    """Permanent Telegram API errors should not be retried."""
    transport = FakeHttpTransport(
        [FakeResponse(400, {"ok": False, "description": "chat not found"})]
    )
    sender = _sender(transport)

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_FAILED
    assert result.error_reason == TELEGRAM_ERROR_API
    assert result.attempts == 1
    assert len(transport.calls) == 1


@pytest.mark.asyncio
async def test_sender_rate_limit_retries_once_then_fails() -> None:
    """Telegram 429 should be retried once and then fail as rate-limited."""
    transport = FakeHttpTransport(
        [
            FakeResponse(429, {"ok": False, "description": "too many"}, {"Retry-After": "0"}),
            FakeResponse(429, {"ok": False, "description": "too many"}, {"Retry-After": "0"}),
        ]
    )
    sender = _sender(transport)

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_FAILED
    assert result.error_reason == TELEGRAM_ERROR_RATE_LIMITED_EXHAUSTED
    assert result.attempts == 2


@pytest.mark.asyncio
async def test_sender_disabled_skips_without_transport_call() -> None:
    """Disabled sender should return skipped without making HTTP calls."""
    transport = FakeHttpTransport(
        [FakeResponse(200, {"ok": True, "result": {"message_id": 323}})]
    )
    sender = TelegramBaseSender(
        client=TelegramHttpClient(
            bot_token=FAKE_TOKEN,
            timeout_ms=5000,
            transport=transport,
        ),
        chat_id=FAKE_CHAT_ID,
        enabled=False,
    )

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_SKIPPED_DISABLED
    assert result.telegram_message_id is None
    assert result.error_reason is None
    assert result.attempts == 0
    assert transport.calls == []


@pytest.mark.asyncio
async def test_sender_logs_no_token(caplog: pytest.LogCaptureFixture) -> None:
    """Sender should not log token values while converting errors to results."""
    transport = FakeHttpTransport([httpx.ConnectError(f"connect {FAKE_TOKEN}")])
    sender = _sender(transport, retry_budget=0)

    result = await sender.send(_event())

    assert result.status == TELEGRAM_STATUS_FAILED
    assert FAKE_TOKEN not in caplog.text


def _sender(transport: FakeHttpTransport, retry_budget: int = 1) -> TelegramBaseSender:
    """Build a sender with fake transport."""
    return TelegramBaseSender(
        client=TelegramHttpClient(
            bot_token=FAKE_TOKEN,
            timeout_ms=5000,
            transport=transport,
        ),
        chat_id=FAKE_CHAT_ID,
        retry_budget=retry_budget,
    )


def _event() -> DispatchEvent:
    """Build a fixed dispatch event."""
    return DispatchEvent(
        pattern_trigger_id=1,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={},
    )
