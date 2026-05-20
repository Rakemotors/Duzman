from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.ai.cache import lookup_cached_explanation
from duzman.ai.cost_limiter import BudgetStatus, check_budget
from duzman.db.models import AlertExplanation

NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create a minimal async SQLite schema for explanation table tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.exec_driver_sql(
            """
            CREATE TABLE alert_explanations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_trigger_id INTEGER NOT NULL,
                alert_delivery_id INTEGER,
                status VARCHAR(32) NOT NULL,
                model VARCHAR(64),
                cache_key VARCHAR(64) NOT NULL,
                prompt_hash VARCHAR(64) NOT NULL,
                prompt_context_json JSON,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                text TEXT,
                error_message TEXT,
                created_at DATETIME NOT NULL,
                started_at DATETIME,
                completed_at DATETIME
            )
            """
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_check_budget_allows_cap_minus_one(session: AsyncSession) -> None:
    """Budget should remain OK below both hard caps."""
    for index in range(9):
        session.add(_row(index, status="completed", created_at=NOW - timedelta(minutes=10)))
    await session.flush()

    assert await check_budget(session, max_per_hour=10, max_per_day=50, now=NOW) == BudgetStatus.OK


@pytest.mark.asyncio
async def test_check_budget_blocks_hour_cap(session: AsyncSession) -> None:
    """Hour cap should block when counted statuses reach the limit."""
    for index in range(10):
        session.add(_row(index, status="failed", created_at=NOW - timedelta(minutes=10)))
    await session.flush()

    assert (
        await check_budget(session, max_per_hour=10, max_per_day=50, now=NOW)
        == BudgetStatus.EXCEEDED_HOUR
    )


@pytest.mark.asyncio
async def test_check_budget_ignores_reused_cache_and_skipped(session: AsyncSession) -> None:
    """Cache and skipped rows should not consume Anthropic budget."""
    for index, status in enumerate(
        ("reused_cache", "skipped_cost_cap", "skipped_no_base_message")
    ):
        session.add(_row(index, status=status, created_at=NOW - timedelta(minutes=10)))
    await session.flush()

    assert await check_budget(session, max_per_hour=1, max_per_day=1, now=NOW) == BudgetStatus.OK


@pytest.mark.asyncio
async def test_lookup_cached_explanation_returns_newest_hit(session: AsyncSession) -> None:
    """Cache lookup should return newest completed text inside the window."""
    session.add(_row(1, status="completed", text="old", created_at=NOW - timedelta(minutes=10)))
    session.add(_row(2, status="completed", text="new", created_at=NOW - timedelta(minutes=1)))
    await session.flush()

    cached = await lookup_cached_explanation(session, "cache", window_minutes=15, now=NOW)

    assert cached is not None
    assert cached.text == "new"


@pytest.mark.asyncio
async def test_lookup_cached_explanation_misses_expired_rows(session: AsyncSession) -> None:
    """Cache lookup should ignore rows older than the configured window."""
    session.add(_row(1, status="completed", text="old", created_at=NOW - timedelta(minutes=30)))
    await session.flush()

    assert await lookup_cached_explanation(session, "cache", window_minutes=15, now=NOW) is None


def _row(
    index: int,
    *,
    status: str,
    created_at: datetime,
    text: str | None = "cached",
) -> AlertExplanation:
    """Build one AlertExplanation row for budget/cache tests."""
    return AlertExplanation(
        pattern_trigger_id=1000 + index,
        alert_delivery_id=None,
        status=status,
        model="claude-sonnet-4-6",
        cache_key="cache",
        prompt_hash=f"hash-{index}",
        prompt_context_json={},
        text=text,
        created_at=created_at,
    )
