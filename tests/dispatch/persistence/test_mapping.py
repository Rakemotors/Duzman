# tests/dispatch/persistence/test_mapping.py
# Dispatch persistence mapping tests. Verifies pure conversion from dispatch
# event and Telegram result into alert_deliveries row data.
"""Tests for dispatch persistence mapping."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.persistence.mapping import delivery_row_from_telegram_result
from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SENT,
    DELIVERY_STATUS_SKIPPED_DISABLED,
    TELEGRAM_CHANNEL,
)
from duzman.dispatch.telegram.result import TelegramSendResult

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_sent_result_maps_to_sent_delivery_row() -> None:
    """A sent Telegram result should map message id and sent_at."""
    row = delivery_row_from_telegram_result(
        event=_event(),
        result=TelegramSendResult(
            status="sent",
            telegram_message_id=123,
            error_reason=None,
            attempts=1,
        ),
        now=NOW,
    )

    assert row.pattern_trigger_id == 1
    assert row.channel == TELEGRAM_CHANNEL
    assert row.status == DELIVERY_STATUS_SENT
    assert row.telegram_message_id == 123
    assert row.sent_at == NOW
    assert row.error_message is None


def test_failed_result_maps_to_failed_delivery_row() -> None:
    """A failed Telegram result should map error_reason and no sent_at."""
    row = delivery_row_from_telegram_result(
        event=_event(),
        result=TelegramSendResult(
            status="failed",
            telegram_message_id=None,
            error_reason="transport_timeout",
            attempts=2,
        ),
        now=NOW,
    )

    assert row.status == DELIVERY_STATUS_FAILED
    assert row.telegram_message_id is None
    assert row.sent_at is None
    assert row.error_message == "transport_timeout"


def test_skipped_disabled_result_maps_to_skipped_disabled_delivery_row() -> None:
    """A skipped-disabled Telegram result should map without send fields."""
    row = delivery_row_from_telegram_result(
        event=_event(),
        result=TelegramSendResult(
            status="skipped_disabled",
            telegram_message_id=None,
            error_reason=None,
            attempts=0,
        ),
        now=NOW,
    )

    assert row.status == DELIVERY_STATUS_SKIPPED_DISABLED
    assert row.telegram_message_id is None
    assert row.sent_at is None
    assert row.error_message is None


def test_mapping_rejects_naive_now() -> None:
    """Mapping should require caller-supplied timezone-aware now."""
    with pytest.raises(ValueError, match="now must be timezone-aware"):
        delivery_row_from_telegram_result(
            event=_event(),
            result=TelegramSendResult(
                status="skipped_disabled",
                telegram_message_id=None,
                error_reason=None,
                attempts=0,
            ),
            now=datetime(2026, 6, 1, 12, 0),
        )


@pytest.mark.parametrize(
    ("telegram_status", "delivery_status"),
    [
        ("sent", DELIVERY_STATUS_SENT),
        ("failed", DELIVERY_STATUS_FAILED),
        ("skipped_disabled", DELIVERY_STATUS_SKIPPED_DISABLED),
    ],
)
def test_all_spec2_statuses_map_correctly(
    telegram_status: str,
    delivery_status: str,
) -> None:
    """All Spec 2 status strings should map into Spec 3 delivery statuses."""
    row = delivery_row_from_telegram_result(
        event=_event(),
        result=TelegramSendResult(
            status=telegram_status,
            telegram_message_id=123 if telegram_status == "sent" else None,
            error_reason="telegram_api_error" if telegram_status == "failed" else None,
            attempts=1,
        ),
        now=NOW,
    )

    assert row.status == delivery_status


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
