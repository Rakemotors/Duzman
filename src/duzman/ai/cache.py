# src/duzman/ai/cache.py
# Short-window cache lookup for repeated AI explanations with the same
# normalized reason.
"""Cache lookup for AI explanations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.db.models import AlertExplanation

CACHE_STATUSES = ("completed", "reused_cache")


@dataclass(frozen=True)
class CachedExplanation:
    """Cached explanation text from a recent matching task."""

    text: str
    explanation_id: int
    created_at: datetime


async def lookup_cached_explanation(
    session: AsyncSession,
    cache_key: str,
    *,
    window_minutes: int = 15,
    now: datetime | None = None,
) -> CachedExplanation | None:
    """Return the newest matching cached explanation inside the cache window."""
    current = now or datetime.now(UTC)
    since = current - timedelta(minutes=window_minutes)
    row = await session.scalar(
        select(AlertExplanation)
        .where(
            AlertExplanation.cache_key == cache_key,
            AlertExplanation.status.in_(CACHE_STATUSES),
            AlertExplanation.text.is_not(None),
            AlertExplanation.created_at > since,
        )
        .order_by(AlertExplanation.created_at.desc())
        .limit(1)
    )
    if row is None or row.text is None:
        return None
    return CachedExplanation(
        text=row.text,
        explanation_id=int(row.id),
        created_at=row.created_at,
    )
