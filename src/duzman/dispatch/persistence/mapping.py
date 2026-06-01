# src/duzman/dispatch/persistence/mapping.py
# Dispatch persistence mapping. Converts Spec 1 dispatch events and Spec 2
# Telegram results into validated alert_deliveries row data.
"""Mapping helpers for dispatch delivery persistence."""

from __future__ import annotations

from datetime import datetime

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SENT,
    DELIVERY_STATUS_SKIPPED_DISABLED,
    TELEGRAM_CHANNEL,
    AlertDeliveryRow,
)
from duzman.dispatch.telegram.result import TelegramSendResult


def delivery_row_from_telegram_result(
    *,
    event: DispatchEvent,
    result: TelegramSendResult,
    now: datetime,
) -> AlertDeliveryRow:
    """Build a delivery row from a dispatch event and Telegram send result.

    Parameters:
        event: Dispatch event whose trigger id becomes `alert_deliveries.alert_id`.
        result: Telegram base sender result to persist.
        now: Timezone-aware timestamp supplied by the caller.

    Returns:
        Validated `AlertDeliveryRow` for the Telegram channel.

    Raises:
        ValueError: If `now` is naive or the mapped row is invalid.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    status = _map_status(result.status)
    return AlertDeliveryRow(
        pattern_trigger_id=event.pattern_trigger_id,
        channel=TELEGRAM_CHANNEL,
        status=status,
        telegram_message_id=result.telegram_message_id
        if status == DELIVERY_STATUS_SENT
        else None,
        error_message=result.error_reason if status == DELIVERY_STATUS_FAILED else None,
        sent_at=now if status == DELIVERY_STATUS_SENT else None,
    )


def _map_status(status: str) -> str:
    """Map Telegram result status into delivery row status."""
    if status == DELIVERY_STATUS_SENT:
        return DELIVERY_STATUS_SENT
    if status == DELIVERY_STATUS_FAILED:
        return DELIVERY_STATUS_FAILED
    if status == DELIVERY_STATUS_SKIPPED_DISABLED:
        return DELIVERY_STATUS_SKIPPED_DISABLED
    raise ValueError("unsupported Telegram send status")
