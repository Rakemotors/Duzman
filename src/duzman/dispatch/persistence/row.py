# src/duzman/dispatch/persistence/row.py
# Dispatch persistence row contracts. Defines immutable delivery row inputs
# and idempotent record results for alert_deliveries writes.
"""Dispatch delivery persistence row contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

TELEGRAM_CHANNEL = "telegram"
DELIVERY_STATUS_SENT = "sent"
DELIVERY_STATUS_FAILED = "failed"
DELIVERY_STATUS_SKIPPED_DISABLED = "skipped_disabled"
DELIVERY_STATUS_SENDING = "sending"
DELIVERY_STATUSES = frozenset(
    [
        DELIVERY_STATUS_SENT,
        DELIVERY_STATUS_FAILED,
        DELIVERY_STATUS_SKIPPED_DISABLED,
        DELIVERY_STATUS_SENDING,
    ]
)


@dataclass(frozen=True)
class AlertDeliveryRow:
    """Immutable dispatch-domain representation of one alert_deliveries row."""

    pattern_trigger_id: int
    channel: str
    status: str
    telegram_message_id: int | None
    error_message: str | None
    sent_at: datetime | None

    def __post_init__(self) -> None:
        """Validate delivery row invariants.

        Raises:
            ValueError: If any field violates the Spec 3 persistence contract.
        """
        if self.pattern_trigger_id <= 0:
            raise ValueError("pattern_trigger_id must be positive")
        if not isinstance(self.channel, str) or not self.channel.strip():
            raise ValueError("channel must be a non-empty string")
        if self.status not in DELIVERY_STATUSES:
            raise ValueError("status must be one of the delivery statuses")
        if self.status == DELIVERY_STATUS_SENT and self.channel == TELEGRAM_CHANNEL:
            if self.telegram_message_id is None or self.telegram_message_id <= 0:
                raise ValueError("telegram_message_id must be positive for sent telegram rows")
            _validate_timezone_aware(self.sent_at, "sent_at")
        if self.status != DELIVERY_STATUS_SENT and self.sent_at is not None:
            raise ValueError("sent_at must be None for non-sent rows")
        if self.error_message is not None and not self.error_message.strip():
            raise ValueError("error_message must be a non-empty string when present")


@dataclass(frozen=True)
class RecordDeliveryResult:
    """Outcome of idempotently recording one delivery row."""

    persisted: bool
    row_id: int | None
    existing_row_id: int | None

    def __post_init__(self) -> None:
        """Validate mutually exclusive inserted/conflict result fields.

        Raises:
            ValueError: If the result fields do not match `persisted`.
        """
        if self.persisted:
            if self.row_id is None or self.row_id <= 0:
                raise ValueError("row_id must be positive when persisted is true")
            if self.existing_row_id is not None:
                raise ValueError("existing_row_id must be None when persisted is true")
            return

        if self.row_id is not None:
            raise ValueError("row_id must be None when persisted is false")
        if self.existing_row_id is None or self.existing_row_id <= 0:
            raise ValueError("existing_row_id must be positive when persisted is false")


def _validate_timezone_aware(value: datetime | None, field_name: str) -> None:
    """Validate that a datetime field is present and timezone-aware."""
    if value is None or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
