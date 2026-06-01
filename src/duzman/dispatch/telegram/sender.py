# src/duzman/dispatch/telegram/sender.py
# Telegram base sender. Orchestrates event formatting, Telegram HTTP sending,
# bounded retries, and sanitized immutable send results.
"""Telegram base sender orchestration."""

from __future__ import annotations

import asyncio

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.telegram.client import (
    TelegramApiError,
    TelegramHttpClient,
    TelegramTransportError,
)
from duzman.dispatch.telegram.formatter import format_dispatch_event_for_telegram
from duzman.dispatch.telegram.result import (
    TELEGRAM_ERROR_API,
    TELEGRAM_ERROR_RATE_LIMITED_EXHAUSTED,
    TELEGRAM_STATUS_FAILED,
    TELEGRAM_STATUS_SENT,
    TELEGRAM_STATUS_SKIPPED_DISABLED,
    TelegramSendResult,
)

MAX_RETRY_AFTER_SECONDS = 5.0


class TelegramBaseSender:
    """Send formatted DispatchEvent messages to one Telegram chat."""

    def __init__(
        self,
        *,
        client: TelegramHttpClient,
        chat_id: str,
        retry_budget: int = 1,
        enabled: bool = True,
    ) -> None:
        """Initialize the base sender with injected client and chat id."""
        self._client = client
        self._chat_id = chat_id
        self._retry_budget = max(retry_budget, 0)
        self._enabled = enabled

    async def send(self, event: DispatchEvent) -> TelegramSendResult:
        """Format and send one event, returning a result without raising."""
        if not self._enabled:
            return TelegramSendResult(
                status=TELEGRAM_STATUS_SKIPPED_DISABLED,
                telegram_message_id=None,
                error_reason=None,
                attempts=0,
            )

        text = format_dispatch_event_for_telegram(event)
        attempts = 0
        remaining_retries = self._retry_budget
        last_error_reason = TELEGRAM_ERROR_API
        while True:
            attempts += 1
            try:
                response = await self._client.send_message(
                    chat_id=self._chat_id,
                    text=text,
                )
                return TelegramSendResult(
                    status=TELEGRAM_STATUS_SENT,
                    telegram_message_id=response["message_id"],
                    error_reason=None,
                    attempts=attempts,
                )
            except TelegramTransportError as exc:
                last_error_reason = exc.error_reason
                if remaining_retries <= 0:
                    return _failed_result(last_error_reason, attempts)
                remaining_retries -= 1
            except TelegramApiError as exc:
                last_error_reason = _result_reason_for_api_error(exc)
                if not _is_retryable_api_error(exc) or remaining_retries <= 0:
                    return _failed_result(last_error_reason, attempts)
                remaining_retries -= 1
                if exc.status_code == 429:
                    await asyncio.sleep(_retry_delay_seconds(exc.retry_after_seconds))


def _failed_result(error_reason: str, attempts: int) -> TelegramSendResult:
    """Build a failed Telegram send result."""
    return TelegramSendResult(
        status=TELEGRAM_STATUS_FAILED,
        telegram_message_id=None,
        error_reason=error_reason,
        attempts=attempts,
    )


def _is_retryable_api_error(exc: TelegramApiError) -> bool:
    """Return whether a Telegram API error is retryable by Spec 2 rules."""
    if exc.status_code == 429:
        return True
    return exc.status_code is not None and exc.status_code >= 500


def _result_reason_for_api_error(exc: TelegramApiError) -> str:
    """Map an API error to the bounded send result reason set."""
    if exc.status_code == 429:
        return TELEGRAM_ERROR_RATE_LIMITED_EXHAUSTED
    return exc.error_reason


def _retry_delay_seconds(retry_after_seconds: float | None) -> float:
    """Return capped retry delay for Telegram rate limits."""
    if retry_after_seconds is None:
        return 1.0
    return min(max(retry_after_seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
