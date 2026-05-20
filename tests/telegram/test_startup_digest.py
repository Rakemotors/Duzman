from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import AlertDelivery, PatternTrigger
from duzman.telegram.poller import TelegramAlertPoller
from duzman.telegram.sender import TelegramAlertSender
from tests.telegram.test_sender import FakeTelegramClient, _create_tables, _sleep


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create the minimal SQLite schema required by startup digest tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_startup_digest_sends_and_marks_alerts(session: AsyncSession) -> None:
    """Startup digest should mark sent alerts to avoid restart duplicates."""
    session.add(
        PatternTrigger(
            ts=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
            pattern_name="rsi_overheated",
            asset="BTC",
            severity="WARNING",
            conditions_snapshot={"gate_decision": "ALLOW"},
            alert_sent=False,
        )
    )
    await session.flush()
    client = FakeTelegramClient()
    sender = TelegramAlertSender(client, "42", retry_delays=(0.0,), sleep=_sleep)
    poller = TelegramAlertPoller(sender, rate_limit_seconds=0.0, sleep=_sleep)

    count = await poller.send_startup_digest(session, lookback_hours=24)
    second_count = await poller.send_startup_digest(session, lookback_hours=24)

    deliveries = list(await session.scalars(select(AlertDelivery)))
    assert count == 1
    assert second_count == 0
    assert len(deliveries) == 1
    assert deliveries[0].status == "sent"
    assert client.messages[0].startswith("42:Startup digest")
