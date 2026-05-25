# tests/runtime/test_market_data_scheduler_pattern_tick.py
# Runtime scheduler tests for Phase 1 Pattern Engine tick wiring.
# Verifies registration and offline observation-only execution.
"""Tests for the market data scheduler pattern tick job."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, cast

import pytest
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.patterns.snapshot import AssetMetrics, MetricsSnapshot
from duzman.runtime.market_data_scheduler import (
    HOURLY_PATTERN_TICK_JOB_ID,
    _run_observation_only_pattern_tick_cycle,
    build_market_data_scheduler,
)


@pytest.fixture
def pattern_session_factory() -> Iterator[async_sessionmaker[AsyncSession]]:
    """Create an offline async SQLite session factory for pattern tick tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    asyncio.run(_create_pattern_triggers_schema(engine))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    asyncio.run(engine.dispose())


def test_scheduler_registers_pattern_tick_job() -> None:
    """The runtime scheduler should register the Phase 1 pattern tick job."""
    scheduler = build_market_data_scheduler()

    jobs_by_id = {job.id: job for job in scheduler.get_jobs()}
    pattern_job = jobs_by_id[HOURLY_PATTERN_TICK_JOB_ID]

    assert isinstance(pattern_job.trigger, CronTrigger)
    trigger_text = str(pattern_job.trigger)
    assert "minute='33'" in trigger_text
    assert "second='0'" in trigger_text
    assert str(pattern_job.trigger.timezone) == "UTC"


def test_pattern_tick_job_runs_with_injected_dependencies(
    pattern_session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The registered pattern tick callable should run offline and log completion."""
    scheduler = build_market_data_scheduler(
        pattern_session_factory=pattern_session_factory,
        pattern_snapshot_builder=_empty_snapshot_builder,
    )
    pattern_job = [
        job
        for job in scheduler.get_jobs()
        if job.id == HOURLY_PATTERN_TICK_JOB_ID
    ][0]

    with caplog.at_level(logging.INFO):
        result = pattern_job.func()

    assert result == []
    assert "pattern_tick_cycle_completed" in caplog.text
    assert "allowed_count=0" in caplog.text
    assert "total_matches=0" in caplog.text


def test_pattern_tick_cycle_reuses_single_event_loop_for_shared_engine(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Regression for issue #83: shared AsyncEngine must survive cycle."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        asyncio.run(_create_pattern_triggers_schema(engine))
        base_session_factory = async_sessionmaker(engine, expire_on_commit=False)
        loop_tracker = _CycleLoopTracker()
        session_factory = _LoopCheckingSessionFactory(
            base_session_factory,
            loop_tracker,
        )

        with caplog.at_level(logging.INFO):
            loop_tracker.begin_cycle()
            first_result = _run_observation_only_pattern_tick_cycle(
                session_factory=session_factory,
                snapshot_builder=_executing_empty_snapshot_builder,
            )
            loop_tracker.end_cycle()

            loop_tracker.begin_cycle()
            second_result = _run_observation_only_pattern_tick_cycle(
                session_factory=session_factory,
                snapshot_builder=_executing_empty_snapshot_builder,
            )
            loop_tracker.end_cycle()

        assert first_result == []
        assert second_result == []
        assert caplog.text.count("pattern_tick_cycle_completed") == 2
        assert "pattern_tick_cycle_failed" not in caplog.text
        assert "attached to a different loop" not in caplog.text
        assert "AsyncAdaptedQueuePool" not in caplog.text
    finally:
        asyncio.run(engine.dispose())


async def _create_pattern_triggers_schema(engine: Any) -> None:
    """Create the minimal pattern_triggers schema used by scheduler tests."""
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


async def _empty_snapshot_builder(
    session: AsyncSession,
    assets: list[str],
    now: datetime,
) -> MetricsSnapshot:
    """Return a metrics snapshot without matching metric values."""
    return _empty_snapshot(now)


async def _executing_empty_snapshot_builder(
    session: AsyncSession,
    assets: list[str],
    now: datetime,
) -> MetricsSnapshot:
    """Touch the shared DB session before returning an empty snapshot."""
    await session.execute(select(1))
    return _empty_snapshot(now)


def _empty_snapshot(now: datetime) -> MetricsSnapshot:
    """Build a metrics snapshot without values that could match patterns."""
    return MetricsSnapshot(
        built_at=now.astimezone(UTC),
        assets={"BTC": AssetMetrics(asset="BTC", values={})},
        global_metrics={
            "fear_greed_index": None,
            "btc_dominance": None,
            "btc_dominance_change_7d_pct": None,
        },
    )


class _CycleLoopTracker:
    """Track loop usage within one pattern tick cycle."""

    def __init__(self) -> None:
        self._current_cycle_loop_id: int | None = None

    def begin_cycle(self) -> None:
        """Start a fresh single-cycle loop binding assertion."""
        self._current_cycle_loop_id = None

    def end_cycle(self) -> None:
        """End the current single-cycle loop binding assertion."""
        self._current_cycle_loop_id = None

    def assert_current_loop(self) -> None:
        """Raise if one cycle observes multiple event loop identities."""
        running_loop_id = id(asyncio.get_running_loop())
        if self._current_cycle_loop_id is None:
            self._current_cycle_loop_id = running_loop_id
            return
        if self._current_cycle_loop_id != running_loop_id:
            raise RuntimeError("cross-loop reuse detected")


class _LoopCheckingSessionFactory:
    """Wrap an async session factory with deterministic loop checks."""

    def __init__(
        self,
        base_session_factory: async_sessionmaker[AsyncSession],
        loop_tracker: _CycleLoopTracker,
    ) -> None:
        self._base_session_factory = base_session_factory
        self._loop_tracker = loop_tracker

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Return a session context manager that checks execute/scalar loops."""
        context_manager = _LoopCheckingSessionContext(
            self._base_session_factory(),
            self._loop_tracker,
        )
        return cast(AbstractAsyncContextManager[AsyncSession], context_manager)


class _LoopCheckingSessionContext:
    """Async context manager that yields a loop-checking session proxy."""

    def __init__(
        self,
        base_context_manager: AbstractAsyncContextManager[AsyncSession],
        loop_tracker: _CycleLoopTracker,
    ) -> None:
        self._base_context_manager = base_context_manager
        self._loop_tracker = loop_tracker

    async def __aenter__(self) -> AsyncSession:
        """Enter the wrapped session context and return a loop-checking proxy."""
        base_session = await self._base_context_manager.__aenter__()
        return cast(AsyncSession, _LoopCheckingSession(base_session, self._loop_tracker))

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        """Exit the wrapped session context."""
        return await self._base_context_manager.__aexit__(exc_type, exc, traceback)


class _LoopCheckingSession:
    """Proxy selected AsyncSession methods through loop-binding checks."""

    def __init__(self, base_session: AsyncSession, loop_tracker: _CycleLoopTracker) -> None:
        self._base_session = base_session
        self._loop_tracker = loop_tracker

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute a statement after asserting the current cycle loop."""
        self._loop_tracker.assert_current_loop()
        return await self._base_session.execute(*args, **kwargs)

    async def scalar(self, *args: Any, **kwargs: Any) -> Any:
        """Execute a scalar query after asserting the current cycle loop."""
        self._loop_tracker.assert_current_loop()
        return await self._base_session.scalar(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        """Delegate unwrapped attributes to the base session."""
        return getattr(self._base_session, name)
