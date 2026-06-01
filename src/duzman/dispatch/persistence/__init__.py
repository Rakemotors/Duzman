# src/duzman/dispatch/persistence/__init__.py
# Dispatch persistence package. Exports session-scoped delivery repository,
# row contracts, constants, and mapping helpers for future runtime wiring.
"""Dispatch delivery persistence package."""

from duzman.dispatch.persistence.mapping import delivery_row_from_telegram_result
from duzman.dispatch.persistence.repository import DispatchDeliveryRepository
from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SENT,
    DELIVERY_STATUS_SKIPPED_DISABLED,
    DELIVERY_STATUSES,
    TELEGRAM_CHANNEL,
    AlertDeliveryRow,
    RecordDeliveryResult,
)

__all__ = [
    "DELIVERY_STATUSES",
    "DELIVERY_STATUS_FAILED",
    "DELIVERY_STATUS_SENT",
    "DELIVERY_STATUS_SKIPPED_DISABLED",
    "TELEGRAM_CHANNEL",
    "AlertDeliveryRow",
    "DispatchDeliveryRepository",
    "RecordDeliveryResult",
    "delivery_row_from_telegram_result",
]
