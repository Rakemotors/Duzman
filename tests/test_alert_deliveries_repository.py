from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import PatternTrigger
from duzman.db.repositories.alert_deliveries import AlertDeliveryRepository
from tests.telegram.test_sender import _create_tables


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create the minimal SQLite schema required by delivery repository tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_list_pending_alerts_filters_terminal_deliveries(session: AsyncSession) -> None:
    """Pending query should return ALLOW alerts without terminal deliveries."""
    first = await _insert_alert(session, asset="BTC")
    second = await _insert_alert(session, asset="ETH")
    repository = AlertDeliveryRepository()
    await repository.create_or_update(
        session,
        int(first.id),
        "sent",
        sent_at=datetime.now(UTC),
        now=datetime.now(UTC),
    )

    pending = await repository.list_pending_alerts(session)

    assert [alert.id for alert in pending] == [second.id]


async def _insert_alert(session: AsyncSession, *, asset: str) -> PatternTrigger:
    """Insert one ALLOW PatternTrigger row."""
    alert = PatternTrigger(
        ts=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        pattern_name="rsi_overheated",
        asset=asset,
        severity="WARNING",
        conditions_snapshot={"gate_decision": "ALLOW"},
        alert_sent=False,
    )
    session.add(alert)
    await session.flush()
    return alert
