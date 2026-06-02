# tests/scheduler/test_hourly_tick_alert_gate.py
# Pattern scheduler integration tests. Verifies AlertGate decisions are
# committed per match before allowed matches are dispatched.
"""Tests for hourly Pattern Engine AlertGate integration."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import PatternTrigger
from duzman.db.repositories import PatternTriggerRepository
from duzman.patterns.alert_gate import AlertGate, GateDecision
from duzman.patterns.evaluation import PatternMatch
from duzman.patterns.models import Condition, ConditionGroup, PatternDefinition
from duzman.scheduler.hourly_tick import dispatch_events_for_tick, gate_pattern_matches

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class TriggerSeed:
    """Minimal persisted trigger input for integration test setup."""

    pattern_name: str = "test_pattern"
    asset: str = "BTC"
    severity: str = "WARNING"
    conditions_snapshot: dict[str, float | int] | None = None
    ts: datetime = NOW

    def __post_init__(self) -> None:
        """Populate the default immutable conditions snapshot."""
        if self.conditions_snapshot is None:
            object.__setattr__(self, "conditions_snapshot", {"RSI_4h": 70.0})


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create an offline async SQLite session factory for scheduler tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            """
            CREATE TABLE pattern_triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts DATETIME NOT NULL,
                pattern_name VARCHAR(50) NOT NULL,
                asset VARCHAR(10) NOT NULL,
                severity VARCHAR(10) NOT NULL,
                conditions_snapshot JSON,
                ai_explanation TEXT,
                alert_sent BOOLEAN,
                user_feedback VARCHAR(20),
                user_feedback_at DATETIME
            )
            """
        )

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_allowed_match_dispatched(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """An ALLOW decision should be persisted and dispatched."""
    dispatch = AsyncMock()

    allowed = await _run_matches_tick(
        session_factory,
        [_match()],
        dispatch,
        alert_gate=AlertGate(PatternTriggerRepository()),
    )

    assert allowed == [_match()]
    dispatch.assert_awaited_once_with([_match()])
    rows = await _trigger_rows(session_factory)
    assert [row.conditions_snapshot["gate_decision"] for row in rows] == ["ALLOW"]


@pytest.mark.asyncio
async def test_suppressed_match_not_dispatched(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A suppressed decision should be persisted but not dispatched."""
    repository = PatternTriggerRepository()
    async with session_factory() as session:
        async with session.begin():
            await repository.insert_trigger(
                session,
                TriggerSeed(ts=NOW - timedelta(minutes=10)),
                GateDecision.ALLOW,
            )
    dispatch = AsyncMock()

    allowed = await _run_matches_tick(
        session_factory,
        [_match()],
        dispatch,
        alert_gate=AlertGate(repository),
    )

    assert allowed == []
    dispatch.assert_not_awaited()
    rows = await _trigger_rows(session_factory)
    assert [row.conditions_snapshot["gate_decision"] for row in rows] == [
        "ALLOW",
        "SUPPRESS_COOLDOWN",
    ]


@pytest.mark.asyncio
async def test_two_matches_same_tick_second_sees_first(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The second same-tick match should see the first committed ALLOW row."""
    repository = PatternTriggerRepository()
    dispatch = AsyncMock()
    matches = [_match(), _match()]

    allowed = await _run_matches_tick(
        session_factory,
        matches,
        dispatch,
        patterns=[_pattern(cooldown_hours=0)],
        alert_gate=AlertGate(repository, soft_cap_per_hour=1),
    )

    assert allowed == [_match()]
    dispatch.assert_awaited_once_with([_match()])
    rows = await _trigger_rows(session_factory)
    assert [row.conditions_snapshot["gate_decision"] for row in rows] == [
        "ALLOW",
        "SUPPRESS_SOFT_CAP",
    ]


@pytest.mark.asyncio
async def test_gate_exception_does_not_break_tick(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A gate failure for one match should not stop later matches."""
    repository = PatternTriggerRepository()
    gate = _FirstCallFailsGate(repository)
    dispatch = AsyncMock()
    matches = [_match(asset="BTC"), _match(asset="ETH")]

    allowed = await _run_matches_tick(
        session_factory,
        matches,
        dispatch,
        patterns=[_pattern(applies_to=["BTC", "ETH"])],
        alert_gate=gate,
    )

    assert allowed == [_match(asset="ETH")]
    dispatch.assert_awaited_once_with([_match(asset="ETH")])
    rows = await _trigger_rows(session_factory)
    assert [(row.asset, row.conditions_snapshot["gate_decision"]) for row in rows] == [
        ("ETH", "ALLOW")
    ]


@pytest.mark.asyncio
async def test_dispatch_failure_does_not_rollback_triggers(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Committed trigger rows should survive dispatcher failures."""
    repository = PatternTriggerRepository()
    dispatch = AsyncMock(side_effect=RuntimeError("telegram unavailable"))

    with pytest.raises(RuntimeError, match="telegram unavailable"):
        await _run_matches_tick(
            session_factory,
            [_match()],
            dispatch,
            alert_gate=AlertGate(repository),
        )

    rows = await _trigger_rows(session_factory)
    assert [row.conditions_snapshot["gate_decision"] for row in rows] == ["ALLOW"]

    retry_dispatch = AsyncMock()
    retry_allowed = await _run_matches_tick(
        session_factory,
        [_match()],
        retry_dispatch,
        tick_ts=NOW + timedelta(minutes=30),
        alert_gate=AlertGate(repository),
    )

    assert retry_allowed == []
    retry_dispatch.assert_not_awaited()
    rows = await _trigger_rows(session_factory)
    assert [row.conditions_snapshot["gate_decision"] for row in rows] == [
        "ALLOW",
        "SUPPRESS_COOLDOWN",
    ]


@pytest.mark.asyncio
async def test_tick_ts_consistent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """All trigger rows in one tick should share the same timestamp."""
    await _run_matches_tick(
        session_factory,
        [_match(asset="BTC"), _match(asset="ETH")],
        AsyncMock(),
        patterns=[_pattern(applies_to=["BTC", "ETH"])],
        alert_gate=AlertGate(PatternTriggerRepository()),
    )

    rows = await _trigger_rows(session_factory)
    assert len({row.ts for row in rows}) == 1
    assert rows[0].ts.replace(tzinfo=UTC) == NOW


@pytest.mark.asyncio
async def test_critical_bypasses_soft_cap_in_integration(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """CRITICAL matches should bypass only the soft cap in the scheduler loop."""
    repository = PatternTriggerRepository()
    async with session_factory() as session:
        async with session.begin():
            await repository.insert_trigger(
                session,
                TriggerSeed(pattern_name="other_pattern", ts=NOW - timedelta(minutes=1)),
                GateDecision.ALLOW,
            )
    dispatch = AsyncMock()

    allowed = await _run_matches_tick(
        session_factory,
        [_match(severity="CRITICAL")],
        dispatch,
        patterns=[_pattern(severity="CRITICAL")],
        alert_gate=AlertGate(repository, soft_cap_per_hour=1),
    )

    assert allowed == [_match(severity="CRITICAL")]
    dispatch.assert_awaited_once_with([_match(severity="CRITICAL")])
    rows = await _trigger_rows(session_factory)
    assert [row.conditions_snapshot["gate_decision"] for row in rows] == [
        "ALLOW",
        "ALLOW",
    ]


@pytest.mark.asyncio
async def test_dispatch_events_for_tick_uses_persisted_trigger_ids(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Dispatch events should be built from committed ALLOW trigger rows."""
    repository = PatternTriggerRepository()
    async with session_factory() as session:
        async with session.begin():
            allowed_id = await repository.insert_trigger(
                session,
                TriggerSeed(),
                GateDecision.ALLOW,
            )
            await repository.insert_trigger(
                session,
                TriggerSeed(asset="ETH"),
                GateDecision.SUPPRESS_COOLDOWN,
            )

    events = await dispatch_events_for_tick(session_factory, NOW)

    assert len(events) == 1
    assert events[0].pattern_trigger_id == allowed_id
    assert events[0].asset == "BTC"
    assert events[0].conditions_snapshot is not None
    assert events[0].conditions_snapshot["gate_decision"] == "ALLOW"


async def _run_matches_tick(
    session_factory: async_sessionmaker[AsyncSession],
    matches: Sequence[PatternMatch],
    dispatch: AsyncMock,
    patterns: Sequence[PatternDefinition] | None = None,
    tick_ts: datetime = NOW,
    alert_gate: AlertGate | None = None,
) -> list[PatternMatch]:
    """Run the scheduler gate loop and dispatch allowed matches."""
    repository = PatternTriggerRepository()
    allowed = await gate_pattern_matches(
        session_factory=session_factory,
        pattern_matches=matches,
        patterns=patterns or [_pattern()],
        tick_ts=tick_ts,
        alert_gate=alert_gate or AlertGate(repository),
        pattern_trigger_repository=repository,
    )
    if allowed:
        await dispatch(allowed)
    return allowed


async def _trigger_rows(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[PatternTrigger]:
    """Return persisted pattern trigger rows ordered by id."""
    async with session_factory() as session:
        return list(
            await session.scalars(select(PatternTrigger).order_by(PatternTrigger.id))
        )


def _match(
    asset: str = "BTC",
    severity: str = "WARNING",
    pattern_name: str = "test_pattern",
) -> PatternMatch:
    """Build a deterministic pattern match for scheduler tests."""
    return PatternMatch(
        pattern_name=pattern_name,
        asset=asset,
        severity=severity,
        evaluated_at=NOW,
        conditions_snapshot={"RSI_4h": 70.0},
    )


def _pattern(
    name: str = "test_pattern",
    severity: str = "WARNING",
    applies_to: list[str] | None = None,
    cooldown_hours: float = 2.0,
) -> PatternDefinition:
    """Build a pattern definition matching test pattern matches."""
    return PatternDefinition(
        name=name,
        display_name="Test Pattern",
        severity=severity,
        applies_to=applies_to or ["BTC"],
        cooldown_hours=cooldown_hours,
        conditions=ConditionGroup(
            all=[Condition(metric="RSI_4h", operator=">", value=60)]
        ),
    )


class _FirstCallFailsGate(AlertGate):
    """AlertGate test double that raises once and then delegates normally."""

    def __init__(self, repository: PatternTriggerRepository) -> None:
        super().__init__(repository)
        self._call_count = 0

    async def evaluate(
        self,
        trigger,
        pattern_definition: PatternDefinition,
        session: AsyncSession,
    ) -> GateDecision:
        """Raise on the first call and delegate to AlertGate afterwards."""
        self._call_count += 1
        if self._call_count == 1:
            raise RuntimeError("gate failed")
        return await super().evaluate(trigger, pattern_definition, session)
