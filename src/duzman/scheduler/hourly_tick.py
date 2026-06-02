# src/duzman/scheduler/hourly_tick.py
# Pattern scheduler integration. Builds snapshots, evaluates patterns, gates
# trigger candidates, persists all decisions, and dispatches allowed matches.
"""Run the hourly Pattern Engine tick with AlertGate integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import PatternTrigger
from duzman.db.repositories import PatternTriggerRepository
from duzman.dispatch.contract import DispatchEvent, build_dispatch_event
from duzman.logging_config import get_logger, safe_error_message
from duzman.patterns.alert_gate import AlertGate, GateDecision
from duzman.patterns.config import STAGE_A_ASSETS, load_patterns
from duzman.patterns.evaluation import PatternMatch, evaluate_patterns
from duzman.patterns.models import PatternDefinition
from duzman.patterns.snapshot import MetricsSnapshot, build_snapshot

LOGGER = get_logger(__name__)
DEFAULT_PATTERNS_PATH = Path("config/patterns.yaml")


class SessionFactory(Protocol):
    """Factory that creates async SQLAlchemy session context managers."""

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Return a new async session context manager."""
        ...


SnapshotBuilder = Callable[
    [AsyncSession, list[str], datetime],
    Awaitable[MetricsSnapshot],
]
AlertDispatcher = Callable[[list[DispatchEvent]], Awaitable[object]]


@dataclass
class _TriggerForGate:
    """Adapter exposing PatternMatch data through AlertGate's trigger protocol."""

    pattern_name: str
    asset: str
    severity: str
    conditions_snapshot: dict[str, float | int]
    ts: datetime


async def run_hourly_pattern_tick(
    session_factory: SessionFactory,
    dispatch_alerts: AlertDispatcher | None = None,
    patterns: Sequence[PatternDefinition] | None = None,
    assets: Sequence[str] = tuple(sorted(STAGE_A_ASSETS)),
    tick_ts: datetime | None = None,
    snapshot_builder: SnapshotBuilder = build_snapshot,
    alert_gate: AlertGate | None = None,
    pattern_trigger_repository: PatternTriggerRepository | None = None,
) -> list[PatternMatch]:
    """Run one Pattern Engine tick and dispatch only AlertGate-allowed matches.

    Parameters:
        session_factory: Async SQLAlchemy session factory.
        dispatch_alerts: Async dispatcher for allowed matches; no-op when omitted.
        patterns: Pattern definitions to evaluate, loaded from config when omitted.
        assets: Asset symbols to include in the snapshot.
        tick_ts: Shared UTC timestamp for the full tick, fixed at function entry.
        snapshot_builder: Async function that builds a `MetricsSnapshot`.
        alert_gate: AlertGate instance; one is created when omitted.
        pattern_trigger_repository: Repository used for inserts and default gate.

    Returns:
        Matches allowed by AlertGate and passed to the dispatcher.

    Raises:
        Exception: Propagates dispatcher failures after trigger rows are committed.
    """
    resolved_tick_ts = _ensure_utc(tick_ts or datetime.now(UTC))
    resolved_patterns = list(patterns or load_patterns(DEFAULT_PATTERNS_PATH))
    repository = pattern_trigger_repository or PatternTriggerRepository()
    gate = alert_gate or AlertGate(repository)

    async with session_factory() as session:
        snapshot = await snapshot_builder(session, list(assets), resolved_tick_ts)
    pattern_matches = evaluate_patterns(resolved_patterns, snapshot)

    allowed_matches = await gate_pattern_matches(
        session_factory=session_factory,
        pattern_matches=pattern_matches,
        patterns=resolved_patterns,
        tick_ts=resolved_tick_ts,
        alert_gate=gate,
        pattern_trigger_repository=repository,
    )
    if dispatch_alerts is not None and allowed_matches:
        dispatch_events = await dispatch_events_for_tick(session_factory, resolved_tick_ts)
        if dispatch_events:
            await dispatch_alerts(dispatch_events)
    return allowed_matches


async def dispatch_events_for_tick(
    session_factory: SessionFactory,
    tick_ts: datetime,
) -> list[DispatchEvent]:
    """Return ALLOW dispatch events persisted for one Pattern Engine tick."""
    resolved_tick_ts = _ensure_utc(tick_ts)
    async with session_factory() as session:
        rows = list(
            await session.scalars(
                select(PatternTrigger)
                .where(PatternTrigger.ts == resolved_tick_ts)
                .order_by(PatternTrigger.id)
            )
        )
    return [_dispatch_event_from_trigger(row) for row in rows if _is_allow_trigger(row)]


async def gate_pattern_matches(
    session_factory: SessionFactory,
    pattern_matches: Sequence[PatternMatch],
    patterns: Sequence[PatternDefinition],
    tick_ts: datetime,
    alert_gate: AlertGate,
    pattern_trigger_repository: PatternTriggerRepository,
) -> list[PatternMatch]:
    """Persist AlertGate decisions for matches and return allowed matches only.

    Each match is evaluated and inserted in its own transaction. A committed
    ALLOW decision is therefore visible to the next match in the same tick.
    """
    resolved_tick_ts = _ensure_utc(tick_ts)
    patterns_by_name = {pattern.name: pattern for pattern in patterns}
    allowed_matches: list[PatternMatch] = []
    for match in pattern_matches:
        pattern = patterns_by_name[match.pattern_name]
        trigger = _trigger_from_match(match, resolved_tick_ts)
        try:
            async with session_factory() as session:
                async with session.begin():
                    decision = await alert_gate.evaluate(trigger, pattern, session)
                    await pattern_trigger_repository.insert_trigger(
                        session,
                        trigger,
                        decision,
                    )
                    await _log_gate_decision(
                        match=match,
                        decision=decision,
                        tick_ts=resolved_tick_ts,
                        repository=pattern_trigger_repository,
                        session=session,
                    )
        except Exception as exc:  # noqa: BLE001 - one gate failure must not stop the tick.
            LOGGER.error(
                "alert_gate decision failed",
                exc_info=True,
                extra={
                    "pattern_id": match.pattern_name,
                    "asset": match.asset,
                    "severity": match.severity,
                    "error": safe_error_message(exc),
                },
            )
            continue

        if decision is GateDecision.ALLOW:
            allowed_matches.append(match)
    return allowed_matches


def _trigger_from_match(match: PatternMatch, tick_ts: datetime) -> _TriggerForGate:
    """Build the persistence and gate adapter for one pattern match."""
    return _TriggerForGate(
        pattern_name=match.pattern_name,
        asset=match.asset,
        severity=match.severity,
        conditions_snapshot=dict(match.conditions_snapshot),
        ts=tick_ts,
    )


def _is_allow_trigger(row: PatternTrigger) -> bool:
    """Return whether a persisted trigger row is an AlertGate ALLOW."""
    snapshot = row.conditions_snapshot or {}
    return snapshot.get("gate_decision") == GateDecision.ALLOW.value


def _dispatch_event_from_trigger(row: PatternTrigger) -> DispatchEvent:
    """Build a dispatch event from one persisted pattern trigger row."""
    return build_dispatch_event(
        pattern_trigger_id=int(row.id),
        asset=row.asset,
        pattern_name=row.pattern_name,
        severity=row.severity,
        ts=_ensure_utc(row.ts),
        conditions_snapshot=row.conditions_snapshot,
    )


def _decision_reason(decision: GateDecision) -> str | None:
    """Return the compact suppress reason for logs."""
    return {
        GateDecision.SUPPRESS_COOLDOWN: "cooldown",
        GateDecision.SUPPRESS_HARD_CAP_DAY: "daily_cap",
        GateDecision.SUPPRESS_HARD_CAP_HOUR: "hourly_cap",
        GateDecision.SUPPRESS_SOFT_CAP: "soft_cap",
    }.get(decision)


async def _allow_count_24h(
    repository: PatternTriggerRepository,
    session: AsyncSession,
    tick_ts: datetime,
) -> int:
    """Return the ALLOW count for the current UTC day including this tick."""
    day_start = datetime(tick_ts.year, tick_ts.month, tick_ts.day, tzinfo=UTC)
    return await repository.count_allow_in_window(
        session,
        day_start,
        tick_ts + timedelta(microseconds=1),
    )


async def _log_gate_decision(
    match: PatternMatch,
    decision: GateDecision,
    tick_ts: datetime,
    repository: PatternTriggerRepository,
    session: AsyncSession,
) -> None:
    """Log one AlertGate decision with bounded structured fields."""
    LOGGER.info(
        "alert_gate decision",
        extra={
            "pattern_id": match.pattern_name,
            "asset": match.asset,
            "decision": decision.value,
            "severity": match.severity,
            "reason": _decision_reason(decision),
            "allow_count_24h": await _allow_count_24h(repository, session, tick_ts),
            "last_allow_at": None,
        },
    )


def _ensure_utc(value: datetime) -> datetime:
    """Return a timezone-aware UTC timestamp."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
