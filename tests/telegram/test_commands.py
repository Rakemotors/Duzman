from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import PatternTrigger
from duzman.telegram.commands import TelegramCommandService
from duzman.telegram.config import TelegramSettings
from tests.telegram.test_sender import _create_tables


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create the minimal SQLite schema required by command tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_commands_report_status_and_recent_alerts(session: AsyncSession) -> None:
    """Command service should expose status and recent AlertGate alerts."""
    service = _service()
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

    status = await service.status(session)
    alerts = await service.alerts(session)

    assert "Status: alive" in status
    assert "Recent alerts:" in alerts
    assert "BTC" in alerts


@pytest.mark.asyncio
async def test_mute_unmute_and_snooze_commands_persist_state(session: AsyncSession) -> None:
    """Mute, unmute, and snooze commands should persist singleton state."""
    service = _service()

    assert await service.mute(session) == "Telegram delivery muted."
    assert "snoozed until" in await service.snooze(session, "1h")
    assert await service.unmute(session) == "Telegram delivery unmuted."
    status = await service.status(session)

    assert "Muted: False" in status
    assert "Snooze until: none" in status


def _service() -> TelegramCommandService:
    """Build a command service with deterministic settings."""
    return TelegramCommandService(
        settings=TelegramSettings(
            TELEGRAM_BOT_TOKEN="placeholder",
            TELEGRAM_CHAT_ID="42",
            TELEGRAM_ALERT_POLL_INTERVAL_SECONDS=30,
            TELEGRAM_STARTUP_LOOKBACK_HOURS=24,
            TELEGRAM_ENABLED=True,
        )
    )
