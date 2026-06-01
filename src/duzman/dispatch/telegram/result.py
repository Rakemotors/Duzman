# src/duzman/dispatch/telegram/result.py
# Telegram dispatch result contract. Defines immutable send outcomes and
# bounded error reason constants for the base sender.
"""Telegram send result contract."""

from __future__ import annotations

from dataclasses import dataclass

TELEGRAM_STATUS_SENT = "sent"
TELEGRAM_STATUS_FAILED = "failed"
TELEGRAM_STATUS_SKIPPED_DISABLED = "skipped_disabled"
TELEGRAM_SEND_STATUSES = frozenset(
    [
        TELEGRAM_STATUS_SENT,
        TELEGRAM_STATUS_FAILED,
        TELEGRAM_STATUS_SKIPPED_DISABLED,
    ]
)

TELEGRAM_ERROR_API = "telegram_api_error"
TELEGRAM_ERROR_TIMEOUT = "transport_timeout"
TELEGRAM_ERROR_NETWORK = "transport_network_error"
TELEGRAM_ERROR_UNEXPECTED_RESPONSE = "unexpected_response_shape"
TELEGRAM_ERROR_RATE_LIMITED_EXHAUSTED = "rate_limited_exhausted"
TELEGRAM_ERROR_REASONS = frozenset(
    [
        TELEGRAM_ERROR_API,
        TELEGRAM_ERROR_TIMEOUT,
        TELEGRAM_ERROR_NETWORK,
        TELEGRAM_ERROR_UNEXPECTED_RESPONSE,
        TELEGRAM_ERROR_RATE_LIMITED_EXHAUSTED,
    ]
)


@dataclass(frozen=True)
class TelegramSendResult:
    """Immutable Telegram base-send outcome."""

    status: str
    telegram_message_id: int | None
    error_reason: str | None
    attempts: int

    def __post_init__(self) -> None:
        """Validate result status and bounded error reason values.

        Raises:
            ValueError: If status or error_reason is outside the Spec 2 sets.
        """
        if self.status not in TELEGRAM_SEND_STATUSES:
            raise ValueError("status must be one of the Telegram send statuses")
        if self.error_reason is not None and self.error_reason not in TELEGRAM_ERROR_REASONS:
            raise ValueError("error_reason must be one of the Telegram error reasons")
