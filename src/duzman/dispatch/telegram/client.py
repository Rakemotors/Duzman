# src/duzman/dispatch/telegram/client.py
# Telegram HTTP client. Wraps one Bot API sendMessage call behind an injectable
# async transport and keeps token-bearing URLs out of stored state and errors.
"""Async Telegram Bot API client."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, cast

import httpx

from duzman.dispatch.telegram.result import (
    TELEGRAM_ERROR_API,
    TELEGRAM_ERROR_NETWORK,
    TELEGRAM_ERROR_TIMEOUT,
    TELEGRAM_ERROR_UNEXPECTED_RESPONSE,
)

TELEGRAM_API_BASE_URL = "https://api.telegram.org"
REDACTED_TELEGRAM_TOKEN = "[redacted TELEGRAM_BOT_TOKEN]"


class HttpResponse(Protocol):
    """Minimal HTTP response surface needed by TelegramHttpClient."""

    status_code: int
    headers: Mapping[str, str]

    def json(self) -> object:
        """Return the parsed JSON response body."""
        ...


class HttpTransport(Protocol):
    """Injectable async HTTP transport used by TelegramHttpClient."""

    async def post(
        self,
        *,
        url: str,
        json: Mapping[str, object],
        request_timeout: float,
    ) -> HttpResponse:
        """Send an HTTP POST request and return a response object."""
        ...


class DefaultHttpTransport(HttpTransport):
    """httpx-backed transport for production Telegram HTTP calls."""

    async def post(
        self,
        *,
        url: str,
        json: Mapping[str, object],
        request_timeout: float,
    ) -> HttpResponse:
        """Send an HTTP POST through a short-lived httpx AsyncClient."""
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=json, timeout=request_timeout)
            return cast(HttpResponse, response)


class TelegramApiError(Exception):
    """Sanitized Telegram API failure."""

    def __init__(
        self,
        *,
        error_reason: str,
        message: str,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        """Build a sanitized API exception."""
        super().__init__(message)
        self.error_reason = error_reason
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds

    def __repr__(self) -> str:
        """Return a repr without token-bearing context."""
        return f"{self.__class__.__name__}({str(self)!r})"


class TelegramTransportError(Exception):
    """Sanitized Telegram transport failure."""

    def __init__(self, *, error_reason: str, message: str) -> None:
        """Build a sanitized transport exception."""
        super().__init__(message)
        self.error_reason = error_reason

    def __repr__(self) -> str:
        """Return a repr without token-bearing context."""
        return f"{self.__class__.__name__}({str(self)!r})"


class TelegramHttpClient:
    """Single-purpose async wrapper for Telegram Bot API sendMessage."""

    def __init__(
        self,
        *,
        bot_token: str,
        timeout_ms: int,
        transport: HttpTransport | None = None,
    ) -> None:
        """Initialize the Telegram HTTP client.

        Parameters:
            bot_token: Telegram bot token used only to build the call URL.
            timeout_ms: Request timeout in milliseconds.
            transport: Optional fake or custom HTTP transport.
        """
        self._bot_token = bot_token
        self._timeout_ms = timeout_ms
        self._transport: HttpTransport = transport or DefaultHttpTransport()

    def __repr__(self) -> str:
        """Return a repr that never exposes the bot token."""
        return f"{self.__class__.__name__}(bot_token={REDACTED_TELEGRAM_TOKEN!r})"

    async def send_message(self, *, chat_id: str, text: str) -> dict[str, Any]:
        """Send one Telegram message and return the parsed result object.

        Raises:
            TelegramApiError: If Telegram returns an API-level failure.
            TelegramTransportError: If the HTTP transport fails.
        """
        url = f"{TELEGRAM_API_BASE_URL}/bot{self._bot_token}/sendMessage"
        payload: dict[str, object] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "MarkdownV2",
            "disable_web_page_preview": True,
        }
        try:
            response = await self._transport.post(
                url=url,
                json=payload,
                request_timeout=self._timeout_ms / 1000,
            )
        except TimeoutError as exc:
            raise TelegramTransportError(
                error_reason=TELEGRAM_ERROR_TIMEOUT,
                message="transport_timeout",
            ) from exc
        except httpx.TimeoutException as exc:
            raise TelegramTransportError(
                error_reason=TELEGRAM_ERROR_TIMEOUT,
                message="transport_timeout",
            ) from exc
        except (httpx.HTTPError, OSError) as exc:
            raise TelegramTransportError(
                error_reason=TELEGRAM_ERROR_NETWORK,
                message="transport_network_error",
            ) from exc

        body = _parse_response_body(response, self._bot_token)
        if response.status_code != 200:
            raise TelegramApiError(
                error_reason=TELEGRAM_ERROR_API,
                message=_api_error_message(response.status_code, body),
                status_code=response.status_code,
                retry_after_seconds=_retry_after_seconds(response.headers, body),
            )

        if body.get("ok") is not True or not isinstance(body.get("result"), dict):
            raise TelegramApiError(
                error_reason=TELEGRAM_ERROR_UNEXPECTED_RESPONSE,
                message="unexpected_response_shape",
                status_code=response.status_code,
            )

        result = body["result"]
        if not isinstance(result.get("message_id"), int):
            raise TelegramApiError(
                error_reason=TELEGRAM_ERROR_UNEXPECTED_RESPONSE,
                message="unexpected_response_shape",
                status_code=response.status_code,
            )
        return dict(result)


def _parse_response_body(response: HttpResponse, bot_token: str) -> dict[str, Any]:
    """Parse a Telegram JSON response into a dictionary."""
    try:
        body = response.json()
    except ValueError as exc:
        raise TelegramApiError(
            error_reason=TELEGRAM_ERROR_UNEXPECTED_RESPONSE,
            message="unexpected_response_shape",
            status_code=response.status_code,
        ) from exc
    if not isinstance(body, dict):
        raise TelegramApiError(
            error_reason=TELEGRAM_ERROR_UNEXPECTED_RESPONSE,
            message="unexpected_response_shape",
            status_code=response.status_code,
        )
    return {
        str(key): _sanitize_nested(value, bot_token)
        for key, value in body.items()
    }


def _api_error_message(status_code: int, body: Mapping[str, object]) -> str:
    """Return a bounded sanitized API error category."""
    description = body.get("description")
    if isinstance(description, str) and description:
        return f"telegram_api_error:{status_code}:{description[:120]}"
    return f"telegram_api_error:{status_code}"


def _retry_after_seconds(
    headers: Mapping[str, str],
    body: Mapping[str, object],
) -> float | None:
    """Extract optional Telegram retry-after seconds."""
    header_value = headers.get("Retry-After") or headers.get("retry-after")
    if header_value is not None:
        try:
            return float(header_value)
        except ValueError:
            return None

    parameters = body.get("parameters")
    if isinstance(parameters, Mapping):
        retry_after = parameters.get("retry_after")
        if isinstance(retry_after, int | float):
            return float(retry_after)
    return None


def _sanitize_nested(value: object, bot_token: str) -> object:
    """Redact bot token occurrences from response content."""
    if isinstance(value, str):
        return _sanitize(value, bot_token)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_nested(nested_value, bot_token)
            for key, nested_value in value.items()
        }
    return value


def _sanitize(value: str, bot_token: str) -> str:
    """Redact bot token occurrences from a string."""
    if not bot_token:
        return value
    return value.replace(bot_token, REDACTED_TELEGRAM_TOKEN)
