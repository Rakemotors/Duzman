from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.ai.explanation_worker import (
    ExplanationWorker,
    pending_explanation_ids,
    reclaim_stale_explanations,
)
from duzman.db.models import AlertExplanation
from tests.ai.test_explanation_service import _create_tables

NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


class FakeService:
    """Worker service test double."""

    def __init__(self) -> None:
        self.processed: list[int] = []

    async def process_task(self, session: AsyncSession, explanation_id: int) -> str:
        """Mark a task completed and record processing order."""
        row = await session.get(AlertExplanation, explanation_id)
        assert row is not None
        row.status = "completed"
        row.completed_at = NOW
        self.processed.append(explanation_id)
        return "completed"


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create an async SQLite session factory for worker tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_pending_explanation_ids_returns_oldest_pending(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Pending lookup should return only pending ids in deterministic order."""
    async with session_factory() as session:
        first = _row(1, "pending", NOW - timedelta(minutes=2))
        second = _row(2, "completed", NOW - timedelta(minutes=1))
        third = _row(3, "pending", NOW)
        session.add_all([first, second, third])
        await session.flush()

        ids = await pending_explanation_ids(session, limit=5)

    assert ids == [first.id, third.id]


@pytest.mark.asyncio
async def test_reclaim_stale_explanations_marks_old_running(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Stale running tasks should be marked failed_stale."""
    async with session_factory() as session:
        stale = _row(
            1,
            "running",
            NOW - timedelta(minutes=20),
            started_at=NOW - timedelta(minutes=20),
        )
        fresh = _row(2, "running", NOW, started_at=NOW)
        session.add_all([stale, fresh])
        await session.flush()

        count = await reclaim_stale_explanations(session, running_stale_minutes=10, now=NOW)
        rows = list(await session.scalars(select(AlertExplanation).order_by(AlertExplanation.id)))

    assert count == 1
    assert rows[0].status == "failed_stale"
    assert rows[1].status == "running"


@pytest.mark.asyncio
async def test_worker_run_once_processes_batch_sequentially(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Worker run_once should process pending tasks through the service."""
    async with session_factory() as session:
        session.add_all([_row(1, "pending", NOW), _row(2, "pending", NOW)])
        await session.commit()

    service = FakeService()
    worker = ExplanationWorker(
        session_factory,
        service,
        poll_seconds=30,
        running_stale_minutes=10,
        now=lambda: NOW,
    )

    processed = await worker.run_once()

    async with session_factory() as session:
        statuses = list(await session.scalars(select(AlertExplanation.status)))

    assert processed == 2
    assert service.processed == [1, 2]
    assert statuses == ["completed", "completed"]


def _row(
    index: int,
    status: str,
    created_at: datetime,
    *,
    started_at: datetime | None = None,
) -> AlertExplanation:
    """Build one worker test row."""
    return AlertExplanation(
        pattern_trigger_id=1000 + index,
        alert_delivery_id=None,
        status=status,
        model=None,
        cache_key=f"cache-{index}",
        prompt_hash=f"hash-{index}",
        prompt_context_json={},
        created_at=created_at,
        started_at=started_at,
    )
