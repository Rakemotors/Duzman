# src/duzman/patterns/alert_gate.py
# Pattern Engine - AlertGate. Applies cooldown and alert-cap policy before
# pattern trigger persistence, without sending Telegram messages.
"""Evaluate Pattern Engine alert-gating decisions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.repositories import PatternTriggerRepository
from duzman.patterns.models import PatternDefinition


class GateDecision(str, Enum):
    """AlertGate decision values stored with pattern trigger snapshots.

    Values map directly to the temporary day-6 source of truth in
    `pattern_triggers.conditions_snapshot.gate_decision`.
    """

    ALLOW = "ALLOW"
    SUPPRESS_COOLDOWN = "SUPPRESS_COOLDOWN"
    SUPPRESS_SOFT_CAP = "SUPPRESS_SOFT_CAP"
    SUPPRESS_HARD_CAP_HOUR = "SUPPRESS_HARD_CAP_HOUR"
    SUPPRESS_HARD_CAP_DAY = "SUPPRESS_HARD_CAP_DAY"


class PatternTriggerInput(Protocol):
    """Structural trigger input consumed by AlertGate.

    The trigger is produced by the Pattern Engine evaluation layer and must carry
    the pattern identity, asset, severity, metric snapshot, and UTC evaluation
    timestamp.
    """

    pattern_name: str
    asset: str
    severity: str
    conditions_snapshot: dict[str, float | int]
    ts: datetime


class AlertGate:
    """Apply cooldown and soft/hard cap policy for evaluated pattern triggers.

    The gate is intentionally side-effect free: it reads counters through
    `PatternTriggerRepository` and returns a `GateDecision`. The caller persists
    the trigger and decision after evaluation.

    Parameters:
        repository: Repository used to query prior ALLOW decisions.
    """

    def __init__(
        self,
        repository: PatternTriggerRepository,
        soft_cap_per_hour: int = 3,
        hard_cap_per_hour: int = 10,
        hard_cap_per_day: int = 30,
    ) -> None:
        """Initialize the gate with repository-backed alert caps.

        Parameters:
            repository: Repository used to query prior ALLOW decisions.
            soft_cap_per_hour: Hourly soft cap bypassed by CRITICAL triggers.
            hard_cap_per_hour: Hourly hard cap applied to all severities.
            hard_cap_per_day: Daily hard cap applied to all severities.
        """
        self.repository = repository
        self.soft_cap_per_hour = soft_cap_per_hour
        self.hard_cap_per_hour = hard_cap_per_hour
        self.hard_cap_per_day = hard_cap_per_day

    async def evaluate(
        self,
        trigger: PatternTriggerInput,
        pattern_definition: PatternDefinition,
        session: AsyncSession,
    ) -> GateDecision:
        """Return the AlertGate decision for a trigger.

        Parameters:
            trigger: Evaluated pattern trigger with a timezone-aware UTC `ts`.
            pattern_definition: Pattern configuration with resolved
                `cooldown_hours`; AlertGate does not apply its own fallback.
            session: Async SQLAlchemy session used only for repository reads.

        Returns:
            The first matching gate decision in the required order: cooldown,
            daily hard cap, hourly hard cap, soft cap, then allow.

        Raises:
            AssertionError: If `trigger.ts` is not timezone-aware UTC.
        """
        _assert_aware_utc(trigger.ts)
        cooldown_window_start = trigger.ts - timedelta(
            hours=pattern_definition.cooldown_hours
        )
        if await self.repository.cooldown_hit(
            session,
            pattern_name=trigger.pattern_name,
            asset=trigger.asset,
            cooldown_window_start=cooldown_window_start,
            now=trigger.ts,
        ):
            return GateDecision.SUPPRESS_COOLDOWN

        counter_window_end = _include_current_tick(trigger.ts)
        daily_count = await self.repository.count_allow_in_window(
            session,
            window_start=_floor_to_day_utc(trigger.ts),
            window_end=counter_window_end,
        )
        if daily_count >= self.hard_cap_per_day:
            return GateDecision.SUPPRESS_HARD_CAP_DAY

        hourly_count = await self.repository.count_allow_in_window(
            session,
            window_start=_floor_to_hour_utc(trigger.ts),
            window_end=counter_window_end,
        )
        if hourly_count >= self.hard_cap_per_hour:
            return GateDecision.SUPPRESS_HARD_CAP_HOUR
        if hourly_count >= self.soft_cap_per_hour and trigger.severity != "CRITICAL":
            return GateDecision.SUPPRESS_SOFT_CAP
        return GateDecision.ALLOW


def _floor_to_hour_utc(ts: datetime) -> datetime:
    """Return the start of the UTC hour for a timestamp."""
    _assert_aware_utc(ts)
    return datetime(ts.year, ts.month, ts.day, ts.hour, 0, 0, tzinfo=timezone.utc)


def _floor_to_day_utc(ts: datetime) -> datetime:
    """Return the start of the UTC day for a timestamp."""
    _assert_aware_utc(ts)
    return datetime(ts.year, ts.month, ts.day, 0, 0, 0, tzinfo=timezone.utc)


def _include_current_tick(ts: datetime) -> datetime:
    """Return a counter upper bound that includes committed rows at `ts`."""
    _assert_aware_utc(ts)
    return ts + timedelta(microseconds=1)


def _assert_aware_utc(ts: datetime) -> None:
    """Assert that a timestamp is timezone-aware UTC."""
    assert ts.tzinfo is not None and ts.utcoffset() is not None, (
        "trigger timestamp must be timezone-aware UTC"
    )
    assert ts.utcoffset() == timedelta(0), "trigger timestamp must be UTC"
