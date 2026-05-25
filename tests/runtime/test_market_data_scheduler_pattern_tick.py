# tests/runtime/test_market_data_scheduler_pattern_tick.py
# Runtime scheduler tests for Phase 1 Pattern Engine tick wiring.
# Verifies registration and offline observation-only execution.
"""Tests for the market data scheduler pattern tick job."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.patterns.snapshot import AssetMetrics, MetricsSnapshot
from duzman.runtime.market_data_scheduler import (
    HOURLY_PATTERN_TICK_JOB_ID,
    build_market_data_scheduler,
)


@pytest.fixture
def pattern_session_factory() -> Iterator[async_sessionmaker[AsyncSession]]:
    """Create an offline async SQLite session factory for pattern tick tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    async def create_schema() -> None:
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

    asyncio.run(create_schema())
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


async def _empty_snapshot_builder(
    session: AsyncSession,
    assets: list[str],
    now: datetime,
) -> MetricsSnapshot:
    """Return a metrics snapshot without matching metric values."""
    return MetricsSnapshot(
        built_at=now.astimezone(UTC),
        assets={"BTC": AssetMetrics(asset="BTC", values={})},
        global_metrics={
            "fear_greed_index": None,
            "btc_dominance": None,
            "btc_dominance_change_7d_pct": None,
        },
    )
