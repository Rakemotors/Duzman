# tests/dispatch/harness/conftest.py
# Dispatch harness fixtures. Provides deterministic events and fake harness
# dependencies without external database, Telegram, or AI configuration.
"""Fixtures for dispatch harness tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.harness import (
    DispatchHarness,
    FakeAIWorker,
    FakePersistence,
    FakeTelegramSender,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def now() -> datetime:
    """Return the fixed harness timestamp."""
    return NOW


@pytest.fixture
async def fake_persistence() -> AsyncIterator[FakePersistence]:
    """Yield an entered in-memory fake persistence context."""
    async with FakePersistence() as persistence:
        yield persistence


@pytest.fixture
def sender() -> FakeTelegramSender:
    """Return a deterministic fake Telegram sender."""
    return FakeTelegramSender()


@pytest.fixture
def ai_worker() -> FakeAIWorker:
    """Return a deterministic fake AI worker."""
    return FakeAIWorker()


@pytest.fixture
def harness(
    sender: FakeTelegramSender,
    ai_worker: FakeAIWorker,
    fake_persistence: FakePersistence,
) -> DispatchHarness:
    """Return a complete dispatch harness."""
    return DispatchHarness(
        sender=sender,
        ai_worker=ai_worker,
        persistence=fake_persistence,
    )


@pytest.fixture
def event() -> DispatchEvent:
    """Return a fixed valid dispatch event."""
    return build_event(pattern_trigger_id=1)


def build_event(pattern_trigger_id: int) -> DispatchEvent:
    """Build a valid dispatch event for a seeded trigger id."""
    return DispatchEvent(
        pattern_trigger_id=pattern_trigger_id,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={"gate_decision": "ALLOW"},
    )
