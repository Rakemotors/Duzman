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
    """Create the minimal SQLite schema required by poller tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_once_sends_only_allow_alerts(session: AsyncSession) -> None:
    """Poller should dispatch ALLOW alerts without touching suppressed rows."""
    await _insert_alert(session, gate_decision="ALLOW")
    await _insert_alert(session, gate_decision="SUPPRESS_COOLDOWN")
    client = FakeTelegramClient()
    sender = TelegramAlertSender(client, "42", retry_delays=(0.0,), sleep=_sleep)
    poller = TelegramAlertPoller(sender, rate_limit_seconds=0.0, sleep=_sleep)

    count = await poller.run_once(session)

    deliveries = list(await session.scalars(select(AlertDelivery)))
    assert count == 1
    assert len(deliveries) == 1
    assert deliveries[0].status == "sent"
    assert len(client.messages) == 1


async def _insert_alert(session: AsyncSession, *, gate_decision: str) -> PatternTrigger:
    """Insert one PatternTrigger row."""
    alert = PatternTrigger(
        ts=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        pattern_name="rsi_overheated",
        asset="BTC",
        severity="WARNING",
        conditions_snapshot={"gate_decision": gate_decision},
        alert_sent=False,
    )
    session.add(alert)
    await session.flush()
    return alert
