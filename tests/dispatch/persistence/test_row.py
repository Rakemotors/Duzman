# tests/dispatch/persistence/test_row.py
# Dispatch persistence row tests. Verifies immutable row contracts and result
# validation before repository writes.
"""Tests for dispatch persistence row contracts."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SENT,
    DELIVERY_STATUS_SKIPPED_DISABLED,
    TELEGRAM_CHANNEL,
    AlertDeliveryRow,
    RecordDeliveryResult,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_alert_delivery_row_sent_success() -> None:
    """A sent Telegram row with message id and sent_at should validate."""
    row = AlertDeliveryRow(
        pattern_trigger_id=1,
        channel=TELEGRAM_CHANNEL,
        status=DELIVERY_STATUS_SENT,
        telegram_message_id=123,
        error_message=None,
        sent_at=NOW,
    )

    assert row.pattern_trigger_id == 1


def test_alert_delivery_row_failed_success() -> None:
    """A failed row with an error message and no sent_at should validate."""
    row = AlertDeliveryRow(
        pattern_trigger_id=1,
        channel=TELEGRAM_CHANNEL,
        status=DELIVERY_STATUS_FAILED,
        telegram_message_id=None,
        error_message="transport_timeout",
        sent_at=None,
    )

    assert row.error_message == "transport_timeout"


def test_alert_delivery_row_skipped_disabled_success() -> None:
    """A skipped-disabled row without send fields should validate."""
    row = AlertDeliveryRow(
        pattern_trigger_id=1,
        channel=TELEGRAM_CHANNEL,
        status=DELIVERY_STATUS_SKIPPED_DISABLED,
        telegram_message_id=None,
        error_message=None,
        sent_at=None,
    )

    assert row.status == DELIVERY_STATUS_SKIPPED_DISABLED


@pytest.mark.parametrize("pattern_trigger_id", [0, -1])
def test_alert_delivery_row_rejects_non_positive_pattern_trigger_id(
    pattern_trigger_id: int,
) -> None:
    """pattern_trigger_id must be positive."""
    with pytest.raises(ValueError, match="pattern_trigger_id must be positive"):
        _sent_row(pattern_trigger_id=pattern_trigger_id)


def test_alert_delivery_row_rejects_empty_channel() -> None:
    """Channel must not be empty."""
    with pytest.raises(ValueError, match="channel must be a non-empty string"):
        _sent_row(channel=" ")


def test_alert_delivery_row_rejects_unknown_status() -> None:
    """Status must be in the bounded delivery status set."""
    with pytest.raises(ValueError, match="status must be one of"):
        _sent_row(status="queued")


def test_alert_delivery_row_rejects_sent_without_sent_at() -> None:
    """Sent Telegram rows require a timezone-aware sent_at."""
    with pytest.raises(ValueError, match="sent_at must be timezone-aware"):
        _sent_row(sent_at=None)


@pytest.mark.parametrize("message_id", [None, 0, -1])
def test_alert_delivery_row_rejects_sent_without_positive_message_id(
    message_id: int | None,
) -> None:
    """Sent Telegram rows require a positive Telegram message id."""
    with pytest.raises(ValueError, match="telegram_message_id must be positive"):
        _sent_row(telegram_message_id=message_id)


def test_alert_delivery_row_rejects_non_sent_with_sent_at() -> None:
    """Non-sent rows must not carry sent_at."""
    with pytest.raises(ValueError, match="sent_at must be None"):
        AlertDeliveryRow(
            pattern_trigger_id=1,
            channel=TELEGRAM_CHANNEL,
            status=DELIVERY_STATUS_FAILED,
            telegram_message_id=None,
            error_message="transport_timeout",
            sent_at=NOW,
        )


def test_alert_delivery_row_rejects_empty_error_message() -> None:
    """Error messages must be non-empty when present."""
    with pytest.raises(ValueError, match="error_message must be a non-empty string"):
        AlertDeliveryRow(
            pattern_trigger_id=1,
            channel=TELEGRAM_CHANNEL,
            status=DELIVERY_STATUS_FAILED,
            telegram_message_id=None,
            error_message=" ",
            sent_at=None,
        )


def test_alert_delivery_row_is_immutable() -> None:
    """AlertDeliveryRow should be frozen."""
    row = _sent_row()

    with pytest.raises(FrozenInstanceError):
        row.status = DELIVERY_STATUS_FAILED


def test_record_delivery_result_persisted_success() -> None:
    """Persisted results should carry row_id only."""
    result = RecordDeliveryResult(persisted=True, row_id=1, existing_row_id=None)

    assert result.row_id == 1


def test_record_delivery_result_conflict_success() -> None:
    """Conflict results should carry existing_row_id only."""
    result = RecordDeliveryResult(persisted=False, row_id=None, existing_row_id=1)

    assert result.existing_row_id == 1


@pytest.mark.parametrize(
    ("persisted", "row_id", "existing_row_id"),
    [
        (True, None, None),
        (True, 1, 2),
        (False, 1, None),
        (False, None, None),
    ],
)
def test_record_delivery_result_rejects_invalid_cases(
    persisted: bool,
    row_id: int | None,
    existing_row_id: int | None,
) -> None:
    """RecordDeliveryResult should enforce mutually exclusive fields."""
    with pytest.raises(ValueError):
        RecordDeliveryResult(
            persisted=persisted,
            row_id=row_id,
            existing_row_id=existing_row_id,
        )


def _sent_row(
    *,
    pattern_trigger_id: int = 1,
    channel: str = TELEGRAM_CHANNEL,
    status: str = DELIVERY_STATUS_SENT,
    telegram_message_id: int | None = 123,
    sent_at: datetime | None = NOW,
) -> AlertDeliveryRow:
    """Build a valid sent row with optional overrides."""
    return AlertDeliveryRow(
        pattern_trigger_id=pattern_trigger_id,
        channel=channel,
        status=status,
        telegram_message_id=telegram_message_id,
        error_message=None,
        sent_at=sent_at,
    )
