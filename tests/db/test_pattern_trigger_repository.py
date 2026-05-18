# tests/db/test_pattern_trigger_repository.py
# Pattern Engine persistence tests. Verifies pattern_triggers inserts and
# AlertGate ALLOW counters using offline aiosqlite sessions.
"""Tests for PatternTriggerRepository."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import PatternTrigger
from duzman.db.repositories import PatternTriggerRepository
from duzman.patterns.alert_gate import GateDecision

NOW = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Trigger:
    """Minimal trigger input persisted by repository tests."""

    pattern_name: str = "pattern_a"
    asset: str = "BTC"
    severity: str = "WARNING"
    conditions_snapshot: dict[str, float | int] | None = None
    ts: datetime = NOW

    def __post_init__(self) -> None:
        """Populate an immutable default conditions snapshot."""
        if self.conditions_snapshot is None:
            object.__setattr__(self, "conditions_snapshot", {"rsi": 70.0})


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create an offline async SQLite session with the pattern_triggers table."""
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
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_insert_trigger_writes_gate_decision(session: AsyncSession) -> None:
    """Inserted trigger rows should include the gate decision and day-6 defaults."""
    repository = PatternTriggerRepository()
    trigger = Trigger()

    row_id = await repository.insert_trigger(session, trigger, GateDecision.ALLOW)
    row = await session.get(PatternTrigger, row_id)

    assert row is not None
    assert row.conditions_snapshot["gate_decision"] == "ALLOW"
    assert row.alert_sent is False
    assert row.ai_explanation is None
    assert row.pattern_name == trigger.pattern_name
    assert row.asset == trigger.asset
    assert row.severity == trigger.severity
    assert row.ts.replace(tzinfo=timezone.utc) == trigger.ts


@pytest.mark.asyncio
async def test_insert_trigger_does_not_mutate_input_snapshot(
    session: AsyncSession,
) -> None:
    """Repository insert should copy the trigger conditions snapshot."""
    repository = PatternTriggerRepository()
    conditions_snapshot = {"rsi": 70.0}
    trigger = Trigger(conditions_snapshot=conditions_snapshot)

    await repository.insert_trigger(session, trigger, GateDecision.ALLOW)

    assert conditions_snapshot == {"rsi": 70.0}


@pytest.mark.asyncio
async def test_count_allow_in_window_counts_only_allow(session: AsyncSession) -> None:
    """Window counters should count only ALLOW gate decisions."""
    repository = PatternTriggerRepository()
    for index in range(2):
        await repository.insert_trigger(
            session,
            Trigger(pattern_name=f"allow_{index}", ts=NOW + timedelta(minutes=index)),
            GateDecision.ALLOW,
        )
    for index in range(3):
        await repository.insert_trigger(
            session,
            Trigger(
                pattern_name=f"suppressed_{index}",
                ts=NOW + timedelta(minutes=10 + index),
            ),
            GateDecision.SUPPRESS_COOLDOWN,
        )

    count = await repository.count_allow_in_window(
        session,
        NOW - timedelta(minutes=1),
        NOW + timedelta(hours=1),
    )

    assert count == 2


@pytest.mark.asyncio
async def test_count_allow_in_window_respects_boundaries(session: AsyncSession) -> None:
    """Window counters should include start and exclude end."""
    repository = PatternTriggerRepository()
    window_start = NOW
    window_end = NOW + timedelta(hours=1)
    midpoint = NOW + timedelta(minutes=30)
    for ts in [window_start, midpoint, window_end]:
        await repository.insert_trigger(session, Trigger(ts=ts), GateDecision.ALLOW)

    count = await repository.count_allow_in_window(session, window_start, window_end)

    assert count == 2


@pytest.mark.asyncio
async def test_cooldown_hit_matches_pattern_and_asset(session: AsyncSession) -> None:
    """Cooldown checks should match only the same pattern and asset."""
    repository = PatternTriggerRepository()
    await repository.insert_trigger(
        session,
        Trigger(pattern_name="pattern_a", asset="BTC", ts=NOW - timedelta(minutes=10)),
        GateDecision.ALLOW,
    )

    assert await repository.cooldown_hit(
        session,
        "pattern_a",
        "BTC",
        NOW - timedelta(hours=1),
        NOW,
    )
    assert not await repository.cooldown_hit(
        session,
        "pattern_a",
        "ETH",
        NOW - timedelta(hours=1),
        NOW,
    )
    assert not await repository.cooldown_hit(
        session,
        "pattern_b",
        "BTC",
        NOW - timedelta(hours=1),
        NOW,
    )


@pytest.mark.asyncio
async def test_cooldown_hit_only_allow(session: AsyncSession) -> None:
    """Suppressed trigger rows should not count as cooldown hits."""
    repository = PatternTriggerRepository()
    await repository.insert_trigger(
        session,
        Trigger(pattern_name="pattern_a", asset="BTC", ts=NOW - timedelta(minutes=10)),
        GateDecision.SUPPRESS_COOLDOWN,
    )

    assert not await repository.cooldown_hit(
        session,
        "pattern_a",
        "BTC",
        NOW - timedelta(hours=1),
        NOW,
    )


@pytest.mark.asyncio
async def test_insert_trigger_returns_persisted_id(session: AsyncSession) -> None:
    """Insert should return an id that identifies the persisted row."""
    repository = PatternTriggerRepository()

    row_id = await repository.insert_trigger(session, Trigger(), GateDecision.ALLOW)
    ids = list(await session.scalars(select(PatternTrigger.id)))

    assert ids == [row_id]
