# src/duzman/dispatch/contract.py
# Dispatch contract. Defines immutable event/result structures and the
# dispatcher protocol without database, network, or runtime dependencies.
"""Pure dispatch event and result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

ConditionsSnapshot = dict[str, object]


@dataclass(frozen=True)
class DispatchEvent:
    """Immutable event passed to dispatch implementations."""

    pattern_trigger_id: int
    asset: str
    pattern_name: str
    severity: str
    ts: datetime
    conditions_snapshot: ConditionsSnapshot | None

    def __post_init__(self) -> None:
        """Validate required event fields.

        Raises:
            ValueError: If any required event field is invalid.
        """
        _validate_positive_id(self.pattern_trigger_id)
        _validate_non_empty_string(self.asset, "asset")
        _validate_non_empty_string(self.pattern_name, "pattern_name")
        _validate_non_empty_string(self.severity, "severity")
        _validate_timezone_aware(self.ts)


@dataclass(frozen=True)
class DispatchResult:
    """Immutable status summary returned by a dispatch implementation."""

    telegram_status: str
    explanation_status: str
    errors: tuple[str, ...] = ()


class Dispatcher(Protocol):
    """Protocol implemented by future dispatch orchestration components."""

    async def dispatch(self, event: DispatchEvent) -> DispatchResult:
        """Dispatch one event and return delivery statuses."""
        ...


def build_dispatch_event(
    *,
    pattern_trigger_id: int,
    asset: str,
    pattern_name: str,
    severity: str,
    ts: datetime,
    conditions_snapshot: ConditionsSnapshot | None,
) -> DispatchEvent:
    """Build a validated dispatch event from primitive values.

    Parameters:
        pattern_trigger_id: Positive `pattern_triggers.id` value used as the
            dispatch idempotency anchor.
        asset: Non-empty asset symbol.
        pattern_name: Non-empty stable pattern name.
        severity: Non-empty severity label.
        ts: Timezone-aware trigger timestamp.
        conditions_snapshot: Optional matched-condition snapshot.

    Returns:
        A validated immutable `DispatchEvent`.

    Raises:
        ValueError: If any required primitive value is invalid.
    """
    _validate_positive_id(pattern_trigger_id)
    _validate_non_empty_string(asset, "asset")
    _validate_non_empty_string(pattern_name, "pattern_name")
    _validate_non_empty_string(severity, "severity")
    _validate_timezone_aware(ts)

    return DispatchEvent(
        pattern_trigger_id=pattern_trigger_id,
        asset=asset,
        pattern_name=pattern_name,
        severity=severity,
        ts=ts,
        conditions_snapshot=conditions_snapshot,
    )


def _validate_positive_id(pattern_trigger_id: int) -> None:
    """Validate that pattern_trigger_id is positive."""
    if pattern_trigger_id <= 0:
        raise ValueError("pattern_trigger_id must be positive")


def _validate_non_empty_string(value: str, field_name: str) -> None:
    """Validate that a string field is not empty or whitespace-only."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _validate_timezone_aware(ts: datetime) -> None:
    """Validate that a datetime carries timezone information."""
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("ts must be timezone-aware")
