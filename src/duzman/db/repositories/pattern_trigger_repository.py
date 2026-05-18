# src/duzman/db/repositories/pattern_trigger_repository.py
# Pattern Engine persistence boundary. Stores day-6 trigger rows and reads
# AlertGate counters from pattern_triggers.conditions_snapshot.gate_decision.
"""Repository for persisted Pattern Engine trigger decisions."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import PatternTrigger

if TYPE_CHECKING:
    from duzman.patterns.alert_gate import GateDecision


class PatternTriggerInput(Protocol):
    """Structural trigger input persisted by PatternTriggerRepository.

    The trigger must contain the evaluated pattern identity, asset, severity,
    conditions snapshot, and timezone-aware UTC timestamp.
    """

    pattern_name: str
    asset: str
    severity: str
    conditions_snapshot: dict[str, float | int]
    ts: datetime


class PatternTriggerRepository:
    """Persist pattern trigger rows and query ALLOW counters.

    The repository does not commit transactions. Callers own commit/rollback so
    AlertGate integration can evaluate, insert, and handle failures atomically.
    """

    async def count_allow_in_window(
        self,
        session: AsyncSession,
        window_start: datetime,
        window_end: datetime,
    ) -> int:
        """Count ALLOW decisions in a half-open UTC time window.

        Parameters:
            session: Async SQLAlchemy session.
            window_start: Inclusive lower timestamp bound.
            window_end: Exclusive upper timestamp bound.

        Returns:
            Number of trigger rows with `gate_decision == "ALLOW"`.

        Raises:
            AssertionError: If either timestamp is not timezone-aware UTC.
        """
        _assert_aware_utc(window_start, "window_start")
        _assert_aware_utc(window_end, "window_end")
        statement = (
            select(func.count())
            .select_from(PatternTrigger)
            .where(
                PatternTrigger.ts >= window_start,
                PatternTrigger.ts < window_end,
                _gate_decision_expr(_dialect_name(session)) == "ALLOW",
            )
        )
        count = await session.scalar(statement)
        return int(count or 0)

    async def cooldown_hit(
        self,
        session: AsyncSession,
        pattern_name: str,
        asset: str,
        cooldown_window_start: datetime,
        now: datetime,
    ) -> bool:
        """Return whether a matching ALLOW exists in the cooldown window.

        Parameters:
            session: Async SQLAlchemy session.
            pattern_name: Pattern identity used in the dedup key.
            asset: Asset symbol used in the dedup key.
            cooldown_window_start: Inclusive lower cooldown bound.
            now: Exclusive upper cooldown bound.

        Returns:
            True when the same `(pattern_name, asset)` already has an ALLOW row.

        Raises:
            AssertionError: If either timestamp is not timezone-aware UTC.
        """
        _assert_aware_utc(cooldown_window_start, "cooldown_window_start")
        _assert_aware_utc(now, "now")
        statement = (
            select(PatternTrigger.id)
            .where(
                PatternTrigger.pattern_name == pattern_name,
                PatternTrigger.asset == asset,
                PatternTrigger.ts >= cooldown_window_start,
                PatternTrigger.ts < now,
                _gate_decision_expr(_dialect_name(session)) == "ALLOW",
            )
            .limit(1)
        )
        return await session.scalar(statement) is not None

    async def insert_trigger(
        self,
        session: AsyncSession,
        trigger: PatternTriggerInput,
        gate_decision: GateDecision,
    ) -> int:
        """Insert one pattern trigger row with the AlertGate decision.

        Parameters:
            session: Async SQLAlchemy session.
            trigger: Evaluated trigger to persist. Its `conditions_snapshot` is
                copied before adding `gate_decision`.
            gate_decision: Decision returned by AlertGate.

        Returns:
            Database id of the inserted `pattern_triggers` row.

        Raises:
            AssertionError: If `trigger.ts` is not timezone-aware UTC.
        """
        _assert_aware_utc(trigger.ts, "trigger.ts")
        conditions_snapshot = dict(trigger.conditions_snapshot)
        conditions_snapshot["gate_decision"] = gate_decision.value
        row = PatternTrigger(
            ts=trigger.ts,
            pattern_name=trigger.pattern_name,
            asset=trigger.asset,
            severity=trigger.severity,
            conditions_snapshot=conditions_snapshot,
            alert_sent=False,
            ai_explanation=None,
        )
        session.add(row)
        await session.flush()
        return int(row.id)


def _gate_decision_expr(dialect_name: str) -> ColumnElement[str]:
    """Return a dialect-specific JSON expression for gate_decision."""
    if dialect_name == "sqlite":
        return func.json_extract(PatternTrigger.conditions_snapshot, "$.gate_decision")
    return PatternTrigger.conditions_snapshot.op("->>")("gate_decision")


def _dialect_name(session: AsyncSession) -> str:
    """Return the bound SQL dialect name for an async session."""
    return session.get_bind().dialect.name


def _assert_aware_utc(ts: datetime, field_name: str) -> None:
    """Assert that a repository timestamp is timezone-aware UTC."""
    assert ts.tzinfo is not None and ts.utcoffset() is not None, (
        f"{field_name} must be timezone-aware UTC"
    )
    assert ts.utcoffset() == timedelta(0), f"{field_name} must be UTC"
