# src/duzman/ai/cost_limiter.py
# Cost-cap accounting for AI explanations. Counts terminal Anthropic attempts
# inside rolling hourly and daily budget windows.
"""Hard cost caps for AI explanation tasks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import AlertExplanation

COUNTED_STATUSES = ("completed", "failed", "failed_stale")


class BudgetStatus(StrEnum):
    """Budget result for an explanation task."""

    OK = "OK"
    EXCEEDED_HOUR = "EXCEEDED_HOUR"
    EXCEEDED_DAY = "EXCEEDED_DAY"


async def check_budget(
    session: AsyncSession,
    *,
    max_per_hour: int = 10,
    max_per_day: int = 50,
    now: datetime | None = None,
) -> BudgetStatus:
    """Return whether another Anthropic explanation call is within budget."""
    current = now or datetime.now(UTC)
    hour_count = await _count_since(session, current - timedelta(hours=1))
    if hour_count >= max_per_hour:
        return BudgetStatus.EXCEEDED_HOUR

    day_count = await _count_since(session, current - timedelta(days=1))
    if day_count >= max_per_day:
        return BudgetStatus.EXCEEDED_DAY
    return BudgetStatus.OK


async def _count_since(session: AsyncSession, since: datetime) -> int:
    """Count statuses that consume explanation budget since a timestamp."""
    budget_timestamp = _budget_window_timestamp()
    count = await session.scalar(
        select(func.count())
        .select_from(AlertExplanation)
        .where(
            AlertExplanation.status.in_(COUNTED_STATUSES),
            budget_timestamp > since,
        )
    )
    return int(count or 0)


def _budget_window_timestamp() -> object:
    """Return the timestamp used for retry-aware budget windows."""
    return func.coalesce(AlertExplanation.completed_at, AlertExplanation.created_at)
