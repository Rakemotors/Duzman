from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.db.models import AlertDelivery, AlertExplanation, PatternTrigger
from duzman.telegram.sender import TelegramAlertSender


class FakeTelegramClient:
    """Telegram client test double."""

    def __init__(self, *, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.messages: list[str] = []
        self.replies: list[int | None] = []
        self.next_message_id = 100

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> int:
        """Capture or fail a message send."""
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("temporary telegram failure")
        self.messages.append(f"{chat_id}:{text}")
        self.replies.append(reply_to_message_id)
        message_id = self.next_message_id
        self.next_message_id += 1
        return message_id


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create the minimal SQLite schema required by sender tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_send_alert_records_success(session: AsyncSession) -> None:
    """Successful sends should create a sent delivery row."""
    alert = await _insert_alert(session)
    client = FakeTelegramClient()
    sender = TelegramAlertSender(client, "42", retry_delays=(0.0,), sleep=_sleep)

    status = await sender.send_alert(session, alert)
    await session.commit()

    delivery = await session.scalar(select(AlertDelivery))
    assert status == "sent"
    assert delivery is not None
    assert delivery.status == "sent"
    assert delivery.telegram_message_id == 100
    assert client.messages
    assert client.replies == [None]


@pytest.mark.asyncio
async def test_send_alert_marks_snoozed_when_muted(session: AsyncSession) -> None:
    """Muted channel state should persist a snoozed delivery without sending."""
    alert = await _insert_alert(session)
    await session.execute(
        text(
            "INSERT INTO telegram_channel_state "
            "(id, enabled, muted, updated_at) VALUES (1, 1, 1, CURRENT_TIMESTAMP)"
        )
    )
    client = FakeTelegramClient()
    sender = TelegramAlertSender(client, "42", retry_delays=(0.0,), sleep=_sleep)

    status = await sender.send_alert(session, alert)

    delivery = await session.scalar(select(AlertDelivery))
    assert status == "snoozed"
    assert delivery is not None
    assert delivery.status == "snoozed"
    assert client.messages == []


@pytest.mark.asyncio
async def test_send_alert_retries_then_records_failure(session: AsyncSession) -> None:
    """Repeated client failures should leave a failed delivery row."""
    alert = await _insert_alert(session)
    client = FakeTelegramClient(fail_times=3)
    sender = TelegramAlertSender(client, "42", retry_delays=(0.0, 0.0, 0.0), sleep=_sleep)

    status = await sender.send_alert(session, alert)

    delivery = await session.scalar(select(AlertDelivery))
    assert status == "failed"
    assert delivery is not None
    assert delivery.status == "failed"
    assert "temporary telegram failure" in (delivery.error_message or "")


@pytest.mark.asyncio
async def test_send_alert_creates_pending_explanation_when_enabled(
    session: AsyncSession,
) -> None:
    """Successful sends should enqueue one day-8 explanation task when enabled."""
    alert = await _insert_alert(session)
    client = FakeTelegramClient()
    sender = TelegramAlertSender(
        client,
        "42",
        retry_delays=(0.0,),
        sleep=_sleep,
        ai_explanations_enabled=True,
        anthropic_api_key_configured=True,
    )

    assert await sender.send_alert(session, alert) == "sent"
    assert await sender.send_alert(session, alert) == "sent"

    explanations = list(await session.scalars(select(AlertExplanation)))
    assert len(explanations) == 1
    assert explanations[0].status == "pending"
    assert explanations[0].alert_delivery_id is not None


@pytest.mark.asyncio
async def test_send_explanation_replies_to_base_message() -> None:
    """AI explanations should be sent as replies to the base Telegram alert."""
    factory = await _session_factory()
    async with factory() as session:
        alert = await _insert_alert(session)
        delivery = AlertDelivery(
            alert_id=int(alert.id),
            channel="telegram",
            status="sent",
            telegram_message_id=456,
        )
        session.add(delivery)
        await session.commit()
        delivery_id = int(delivery.id)

    client = FakeTelegramClient()
    sender = TelegramAlertSender(client, "42", session_factory=factory)

    await sender.send_explanation(delivery_id, "AI text")

    assert client.messages == ["42:🤖 Объяснение:\n\nAI text"]
    assert client.replies == [456]


@pytest.mark.asyncio
async def test_send_explanation_skips_missing_base_message() -> None:
    """Missing base message ids should not send a Telegram explanation."""
    factory = await _session_factory()
    async with factory() as session:
        alert = await _insert_alert(session)
        delivery = AlertDelivery(
            alert_id=int(alert.id),
            channel="telegram",
            status="sent",
            telegram_message_id=None,
        )
        session.add(delivery)
        await session.commit()
        delivery_id = int(delivery.id)

    client = FakeTelegramClient()
    sender = TelegramAlertSender(client, "42", session_factory=factory)

    await sender.send_explanation(delivery_id, "AI text")

    assert client.messages == []
    assert client.replies == []


async def _insert_alert(session: AsyncSession) -> PatternTrigger:
    """Insert one ALLOW PatternTrigger row."""
    alert = PatternTrigger(
        ts=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        pattern_name="rsi_overheated",
        asset="BTC",
        severity="WARNING",
        conditions_snapshot={"gate_decision": "ALLOW", "RSI_4h": 82},
        alert_sent=False,
    )
    session.add(alert)
    await session.flush()
    return alert


async def _sleep(_: float) -> None:
    """No-op async sleeper for retry tests."""


async def _session_factory() -> async_sessionmaker[AsyncSession]:
    """Create an offline async SQLite session factory for sender tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    return async_sessionmaker(engine, expire_on_commit=False)


async def _create_tables(connection: Any) -> None:
    """Create the minimal Telegram delivery schema."""
    await connection.exec_driver_sql(
        """
        CREATE TABLE pattern_triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME NOT NULL,
            pattern_name VARCHAR(50) NOT NULL,
            asset VARCHAR(10) NOT NULL,
            severity VARCHAR(10) NOT NULL,
            conditions_snapshot JSON,
            ai_explanation TEXT,
            alert_sent BOOLEAN,
            user_feedback VARCHAR(20),
            user_feedback_at DATETIME
        )
        """
    )
    await connection.exec_driver_sql(
        """
        CREATE TABLE alert_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            channel VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            sent_at DATETIME,
            telegram_message_id BIGINT,
            ack_at DATETIME,
            snooze_until DATETIME,
            error_message TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            UNIQUE(alert_id, channel)
        )
        """
    )
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
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            started_at DATETIME,
            completed_at DATETIME
        )
        """
    )
    await connection.exec_driver_sql(
        """
        CREATE TABLE telegram_channel_state (
            id SMALLINT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT 1,
            muted BOOLEAN NOT NULL DEFAULT 0,
            snooze_until DATETIME,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
        """
    )
