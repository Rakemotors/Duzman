# src/duzman/ai/explanation_worker.py
# Background worker for AI explanation tasks. Polls pending rows sequentially
# and recovers stale running rows.
"""Background worker for AI explanation tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from duzman.ai.explanation_service import ExplanationService
from duzman.db.models import AlertExplanation

LOGGER = logging.getLogger(__name__)


class ExplanationTaskService(Protocol):
    """Processing capability required by the worker."""

    async def process_task(self, session: AsyncSession, explanation_id: int) -> str | None:
        """Process one pending explanation task."""


class ExplanationWorker:
    """Poll and process AI explanation tasks sequentially."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        service: ExplanationTaskService,
        *,
        poll_seconds: int = 30,
        running_stale_minutes: int = 10,
        batch_size: int = 5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Create an explanation worker with explicit dependencies."""
        self._session_factory = session_factory
        self._service = service
        self._poll_seconds = poll_seconds
        self._running_stale_minutes = running_stale_minutes
        self._batch_size = batch_size
        self._sleep = sleep
        self._now = now

    async def run_once(self) -> int:
        """Run one worker tick and return the number of pending tasks processed."""
        async with self._session_factory() as session:
            await reclaim_stale_explanations(
                session,
                running_stale_minutes=self._running_stale_minutes,
                now=self._now(),
            )
            ids = await pending_explanation_ids(session, limit=self._batch_size)
            processed = 0
            for explanation_id in ids:
                await self._service.process_task(session, explanation_id)
                processed += 1
            await session.commit()
            return processed

    async def run_forever(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Run worker ticks until cancelled or stop_event is set."""
        while stop_event is None or not stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                LOGGER.exception("ai_explanation_worker_tick_failed")
            await self._sleep(self._poll_seconds)


async def pending_explanation_ids(session: AsyncSession, *, limit: int = 5) -> list[int]:
    """Return pending explanation ids in creation order."""
    result = await session.scalars(
        select(AlertExplanation.id)
        .where(AlertExplanation.status == "pending")
        .order_by(AlertExplanation.created_at, AlertExplanation.id)
        .limit(limit)
    )
    return [int(explanation_id) for explanation_id in result]


async def reclaim_stale_explanations(
    session: AsyncSession,
    *,
    running_stale_minutes: int,
    now: datetime,
) -> int:
    """Mark stale running explanation tasks as failed_stale."""
    stale_before = now - timedelta(minutes=running_stale_minutes)
    result = await session.execute(
        update(AlertExplanation)
        .where(
            AlertExplanation.status == "running",
            AlertExplanation.started_at < stale_before,
        )
        .values(
            status="failed_stale",
            error_message=f"running exceeded {running_stale_minutes} minutes",
            completed_at=now,
        )
    )
    return int(result.rowcount or 0)


def build_explanation_worker(
    session_factory: async_sessionmaker[AsyncSession],
    service: ExplanationService,
    *,
    poll_seconds: int,
    running_stale_minutes: int,
) -> ExplanationWorker:
    """Build the managed explanation worker without starting it."""
    return ExplanationWorker(
        session_factory,
        service,
        poll_seconds=poll_seconds,
        running_stale_minutes=running_stale_minutes,
    )
