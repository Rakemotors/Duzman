# tests/dispatch/telegram/test_client.py
# Telegram HTTP client tests. Uses fake transports only to exercise API,
# timeout, network, and secret-sanitization behavior.
"""Tests for TelegramHttpClient."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx
import pytest

from duzman.dispatch.telegram.client import (
    HttpResponse,
    TelegramApiError,
    TelegramHttpClient,
    TelegramTransportError,
)

FAKE_TOKEN = "test-bot-token-do-not-use"
FAKE_CHAT_ID = "test-chat-id-12345"


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
    """Fake HTTP transport with queued responses or exceptions."""

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
async def test_client_happy_path() -> None:
    """A successful Telegram response should return the result object."""
    transport = FakeHttpTransport(
        [FakeResponse(200, {"ok": True, "result": {"message_id": 123}})]
    )
    client = TelegramHttpClient(
        bot_token=FAKE_TOKEN,
        timeout_ms=5000,
        transport=transport,
    )

    result = await client.send_message(chat_id=FAKE_CHAT_ID, text="hello")

    assert result == {"message_id": 123}
    assert transport.calls[0]["timeout"] == 5
    assert transport.calls[0]["json"] == {
        "chat_id": FAKE_CHAT_ID,
        "text": "hello",
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }


@pytest.mark.parametrize("status_code", [400, 403, 429])
@pytest.mark.asyncio
async def test_client_api_errors_are_sanitized(status_code: int) -> None:
    """Telegram 4xx responses should raise sanitized API errors."""
    transport = FakeHttpTransport(
        [
            FakeResponse(
                status_code,
                {"ok": False, "description": f"bad token {FAKE_TOKEN}"},
                headers={"Retry-After": "0"},
            )
        ]
    )
    client = TelegramHttpClient(
        bot_token=FAKE_TOKEN,
        timeout_ms=5000,
        transport=transport,
    )

    with pytest.raises(TelegramApiError) as exc_info:
        await client.send_message(chat_id=FAKE_CHAT_ID, text="hello")

    assert exc_info.value.status_code == status_code
    assert FAKE_TOKEN not in str(exc_info.value)
    assert FAKE_TOKEN not in repr(exc_info.value)


@pytest.mark.asyncio
async def test_client_timeout_error_is_sanitized() -> None:
    """Timeout failures should raise a bounded transport error."""
    client = TelegramHttpClient(
        bot_token=FAKE_TOKEN,
        timeout_ms=5000,
        transport=FakeHttpTransport([httpx.TimeoutException(f"timeout {FAKE_TOKEN}")]),
    )

    with pytest.raises(TelegramTransportError) as exc_info:
        await client.send_message(chat_id=FAKE_CHAT_ID, text="hello")

    assert str(exc_info.value) == "transport_timeout"
    assert FAKE_TOKEN not in str(exc_info.value)
    assert FAKE_TOKEN not in repr(exc_info.value)


@pytest.mark.asyncio
async def test_client_network_error_is_sanitized() -> None:
    """Network failures should raise a sanitized transport error."""
    client = TelegramHttpClient(
        bot_token=FAKE_TOKEN,
        timeout_ms=5000,
        transport=FakeHttpTransport([httpx.ConnectError(f"connect {FAKE_TOKEN}")]),
    )

    with pytest.raises(TelegramTransportError) as exc_info:
        await client.send_message(chat_id=FAKE_CHAT_ID, text="hello")

    assert "transport_network_error" in str(exc_info.value)
    assert FAKE_TOKEN not in str(exc_info.value)
    assert FAKE_TOKEN not in repr(exc_info.value)


@pytest.mark.asyncio
async def test_client_unexpected_response_shape() -> None:
    """Malformed Telegram success responses should be rejected."""
    client = TelegramHttpClient(
        bot_token=FAKE_TOKEN,
        timeout_ms=5000,
        transport=FakeHttpTransport([FakeResponse(200, {"ok": True, "result": {}})]),
    )

    with pytest.raises(TelegramApiError, match="unexpected_response_shape"):
        await client.send_message(chat_id=FAKE_CHAT_ID, text="hello")


def test_client_repr_does_not_include_token() -> None:
    """Client repr should not expose the bot token."""
    client = TelegramHttpClient(bot_token=FAKE_TOKEN, timeout_ms=5000)

    assert FAKE_TOKEN not in repr(client)
