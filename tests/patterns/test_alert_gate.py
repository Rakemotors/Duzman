# tests/patterns/test_alert_gate.py
# Pattern Engine - AlertGate tests. Verifies decision ordering and cap behavior
# with a mocked repository and no database.
"""Tests for Pattern Engine AlertGate decisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from duzman.patterns.alert_gate import AlertGate, GateDecision
from duzman.patterns.models import Condition, ConditionGroup, PatternDefinition

NOW = datetime(2026, 5, 18, 12, 34, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Trigger:
    """Minimal trigger input used by AlertGate tests."""

    pattern_name: str = "test_pattern"
    asset: str = "BTC"
    severity: str = "WARNING"
    conditions_snapshot: dict[str, float | int] | None = None
    ts: datetime = NOW

    def __post_init__(self) -> None:
        """Populate an immutable default conditions snapshot."""
        if self.conditions_snapshot is None:
            object.__setattr__(self, "conditions_snapshot", {"RSI_4h": 70.0})


@pytest.mark.asyncio
async def test_allow_when_no_constraints_hit() -> None:
    """ALLOW should be returned when no gate constraint applies."""
    decision = await _evaluate(cooldown_hit=False, counts=[0, 0])

    assert decision == GateDecision.ALLOW


@pytest.mark.asyncio
async def test_suppress_cooldown() -> None:
    """Cooldown should suppress a non-critical trigger before cap checks."""
    decision = await _evaluate(cooldown_hit=True, counts=[30, 10])

    assert decision == GateDecision.SUPPRESS_COOLDOWN


@pytest.mark.asyncio
async def test_suppress_cooldown_even_for_critical() -> None:
    """CRITICAL triggers should not bypass cooldown."""
    decision = await _evaluate(
        trigger=Trigger(severity="CRITICAL"),
        cooldown_hit=True,
        counts=[0, 0],
    )

    assert decision == GateDecision.SUPPRESS_COOLDOWN


@pytest.mark.asyncio
async def test_suppress_hard_cap_day() -> None:
    """Daily hard cap should suppress CRITICAL triggers."""
    decision = await _evaluate(
        trigger=Trigger(severity="CRITICAL"),
        cooldown_hit=False,
        counts=[30],
    )

    assert decision == GateDecision.SUPPRESS_HARD_CAP_DAY


@pytest.mark.asyncio
async def test_suppress_hard_cap_hour() -> None:
    """Hourly hard cap should suppress CRITICAL triggers."""
    decision = await _evaluate(
        trigger=Trigger(severity="CRITICAL"),
        cooldown_hit=False,
        counts=[10, 10],
    )

    assert decision == GateDecision.SUPPRESS_HARD_CAP_HOUR


@pytest.mark.asyncio
async def test_suppress_soft_cap() -> None:
    """Soft cap should suppress non-critical triggers after hard caps pass."""
    decision = await _evaluate(cooldown_hit=False, counts=[3, 3])

    assert decision == GateDecision.SUPPRESS_SOFT_CAP


@pytest.mark.asyncio
async def test_critical_bypasses_soft_cap() -> None:
    """CRITICAL triggers should bypass only the soft cap."""
    decision = await _evaluate(
        trigger=Trigger(severity="CRITICAL"),
        cooldown_hit=False,
        counts=[3, 3],
    )

    assert decision == GateDecision.ALLOW


@pytest.mark.asyncio
async def test_order_cooldown_beats_hard_cap_day() -> None:
    """Cooldown should be evaluated before daily hard cap."""
    repository = _repository(cooldown_hit=True, counts=[30])
    decision = await AlertGate(repository).evaluate(Trigger(), _pattern(), session=None)

    assert decision == GateDecision.SUPPRESS_COOLDOWN
    assert repository.count_allow_in_window.call_count == 0


@pytest.mark.asyncio
async def test_order_hard_cap_day_beats_hard_cap_hour() -> None:
    """Daily hard cap should be evaluated before hourly hard cap."""
    repository = _repository(cooldown_hit=False, counts=[30, 10])
    decision = await AlertGate(repository).evaluate(Trigger(), _pattern(), session=None)

    assert decision == GateDecision.SUPPRESS_HARD_CAP_DAY
    assert repository.count_allow_in_window.call_count == 1


@pytest.mark.asyncio
async def test_order_hard_cap_hour_beats_soft_cap() -> None:
    """Hourly hard cap should be evaluated before soft cap."""
    decision = await _evaluate(cooldown_hit=False, counts=[9, 10])

    assert decision == GateDecision.SUPPRESS_HARD_CAP_HOUR


@pytest.mark.asyncio
async def test_hourly_count_not_requeried() -> None:
    """Soft cap should reuse the hourly count instead of querying again."""
    repository = _repository(cooldown_hit=False, counts=[3, 3, 99])
    decision = await AlertGate(repository).evaluate(Trigger(), _pattern(), session=None)

    assert decision == GateDecision.SUPPRESS_SOFT_CAP
    assert repository.count_allow_in_window.call_count == 2


async def _evaluate(
    cooldown_hit: bool,
    counts: list[int],
    trigger: Trigger | None = None,
) -> GateDecision:
    """Evaluate a trigger against a mocked repository."""
    repository = _repository(cooldown_hit=cooldown_hit, counts=counts)
    return await AlertGate(repository).evaluate(trigger or Trigger(), _pattern(), session=None)


def _repository(cooldown_hit: bool, counts: list[int]) -> object:
    """Return a repository mock with deterministic counter responses."""
    repository = type("RepositoryMock", (), {})()
    repository.cooldown_hit = AsyncMock(return_value=cooldown_hit)
    repository.count_allow_in_window = AsyncMock(side_effect=counts)
    return repository


def _pattern() -> PatternDefinition:
    """Build a pattern definition with an explicit cooldown for tests."""
    return PatternDefinition(
        name="test_pattern",
        display_name="Test Pattern",
        severity="WARNING",
        applies_to=["BTC"],
        cooldown_hours=4.0,
        conditions=ConditionGroup(
            all=[Condition(metric="RSI_4h", operator=">", value=60)]
        ),
    )
