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
async def test_check_budget_ignores_running_self_count(session: AsyncSession) -> None:
    """Running rows should not block the task currently being budget-checked."""
    session.add(
        _row(
            1,
            status="running",
            created_at=NOW,
            started_at=NOW,
        )
    )
    await session.flush()

    assert await check_budget(session, max_per_hour=1, max_per_day=1, now=NOW) == BudgetStatus.OK


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["completed", "failed", "failed_stale"])
async def test_check_budget_counts_terminal_attempt_statuses(
    session: AsyncSession,
    status: str,
) -> None:
    """Terminal Anthropic-attempt rows should consume budget."""
    session.add(_row(1, status=status, created_at=NOW - timedelta(minutes=10)))
    await session.flush()

    assert (
        await check_budget(session, max_per_hour=1, max_per_day=50, now=NOW)
        == BudgetStatus.EXCEEDED_HOUR
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "running",
        "reused_cache",
        "skipped_cost_cap",
        "skipped_disabled",
        "skipped_no_base_message",
    ],
)
async def test_check_budget_ignores_non_attempt_statuses(
    session: AsyncSession,
    status: str,
) -> None:
    """Rows without terminal Anthropic attempts should not consume budget."""
    session.add(_row(1, status=status, created_at=NOW - timedelta(minutes=10)))
    await session.flush()

    assert await check_budget(session, max_per_hour=1, max_per_day=1, now=NOW) == BudgetStatus.OK


@pytest.mark.asyncio
async def test_check_budget_prefers_completed_at_for_retry_accounting(
    session: AsyncSession,
) -> None:
    """Same-row retries should count in the window where they finish."""
    session.add(
        _row(
            1,
            status="completed",
            created_at=NOW - timedelta(hours=2),
            completed_at=NOW - timedelta(minutes=10),
        )
    )
    await session.flush()

    assert (
        await check_budget(session, max_per_hour=1, max_per_day=50, now=NOW)
        == BudgetStatus.EXCEEDED_HOUR
    )


@pytest.mark.asyncio
async def test_check_budget_falls_back_to_created_at_for_legacy_rows(
    session: AsyncSession,
) -> None:
    """Legacy counted terminal rows without completed_at should still count."""
    session.add(
        _row(
            1,
            status="failed",
            created_at=NOW - timedelta(minutes=10),
            completed_at=None,
        )
    )
    await session.flush()

    assert (
        await check_budget(session, max_per_hour=1, max_per_day=50, now=NOW)
        == BudgetStatus.EXCEEDED_HOUR
    )


@pytest.mark.asyncio
async def test_check_budget_blocks_hour_cap(session: AsyncSession) -> None:
    """Hour cap should block when counted statuses reach the hourly limit."""
    for index in range(10):
        session.add(_row(index, status="completed", created_at=NOW - timedelta(minutes=10)))
    await session.flush()

    assert (
        await check_budget(session, max_per_hour=10, max_per_day=50, now=NOW)
        == BudgetStatus.EXCEEDED_HOUR
    )


@pytest.mark.asyncio
async def test_check_budget_blocks_day_cap(session: AsyncSession) -> None:
    """Day cap should block when counted statuses reach the daily limit."""
    session.add(_row(1, status="completed", created_at=NOW - timedelta(hours=2)))
    await session.flush()

    assert (
        await check_budget(session, max_per_hour=10, max_per_day=1, now=NOW)
        == BudgetStatus.EXCEEDED_DAY
    )


@pytest.mark.asyncio
async def test_check_budget_returns_hour_cap_before_day_cap(session: AsyncSession) -> None:
    """Budget status should preserve hour-before-day precedence."""
    session.add(_row(1, status="completed", created_at=NOW - timedelta(minutes=10)))
    await session.flush()

    assert (
        await check_budget(session, max_per_hour=1, max_per_day=1, now=NOW)
        == BudgetStatus.EXCEEDED_HOUR
    )


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
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
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
        started_at=started_at,
        completed_at=completed_at,
    )
