from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.ai.anthropic_client import ExplanationResult
from duzman.ai.explanation_service import ExplanationService, ExplanationServiceConfig
from duzman.ai.explanation_worker import ExplanationWorker
from duzman.db.models import AlertDelivery, AlertExplanation
from duzman.telegram.sender import TelegramAlertSender
from tests.ai.test_explanation_service import FakeAnthropicClient
from tests.telegram.test_sender import FakeTelegramClient, _create_tables, _insert_alert, _sleep

NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create an async SQLite session factory for day-8 integration tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_ai_keeps_day7_delivery_without_explanation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Disabled AI should preserve day-7 Telegram delivery without growing tasks."""
    async with session_factory() as session:
        alert = await _insert_alert(session)
        client = FakeTelegramClient()
        sender = TelegramAlertSender(
            client,
            "42",
            retry_delays=(0.0,),
            sleep=_sleep,
            ai_explanations_enabled=False,
            anthropic_api_key_configured=True,
        )

        status = await sender.send_alert(session, alert)
        await session.commit()

        explanations = list(await session.scalars(select(AlertExplanation)))

    assert status == "sent"
    assert client.messages
    assert explanations == []


@pytest.mark.asyncio
async def test_enabled_ai_without_key_does_not_enqueue_explanation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Enabled AI without Anthropic key should send alerts and skip task creation."""
    async with session_factory() as session:
        alert = await _insert_alert(session)
        client = FakeTelegramClient()
        sender = TelegramAlertSender(
            client,
            "42",
            retry_delays=(0.0,),
            sleep=_sleep,
            ai_explanations_enabled=True,
            anthropic_api_key_configured=False,
        )

        status = await sender.send_alert(session, alert)
        await session.commit()

        explanations = list(await session.scalars(select(AlertExplanation)))

    assert status == "sent"
    assert client.messages
    assert explanations == []


@pytest.mark.asyncio
async def test_delivery_hook_and_worker_send_explanation_reply(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A successful base Telegram alert should enqueue and send one explanation reply."""
    client = FakeTelegramClient()
    sender = TelegramAlertSender(
        client,
        "42",
        session_factory=session_factory,
        retry_delays=(0.0,),
        sleep=_sleep,
        ai_explanations_enabled=True,
        anthropic_api_key_configured=True,
    )
    async with session_factory() as session:
        alert = await _insert_alert(session)
        assert await sender.send_alert(session, alert) == "sent"
        await session.commit()

    service = ExplanationService(
        client=FakeAnthropicClient(
            ExplanationResult(
                text="Structured explanation",
                model_used="claude-sonnet-4-6",
                input_tokens=11,
                output_tokens=22,
                total_tokens=33,
            )
        ),
        telegram_sender=sender,
        config=ExplanationServiceConfig(
            enabled=True,
            api_key_configured=True,
            cache_window_minutes=15,
        ),
        now=lambda: NOW,
    )
    worker = ExplanationWorker(
        session_factory,
        service,
        poll_seconds=30,
        running_stale_minutes=10,
        now=lambda: NOW,
    )

    assert await worker.run_once() == 1

    async with session_factory() as session:
        explanation = await session.scalar(select(AlertExplanation))

    assert explanation is not None
    assert explanation.status == "completed"
    assert explanation.text == "Structured explanation"
    assert client.messages[-1] == "42:🤖 Объяснение:\n\nStructured explanation"
    assert client.replies == [None, 100]


@pytest.mark.asyncio
async def test_worker_skips_explanation_without_base_message_id(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Missing base Telegram message id should skip without Anthropic or reply sends."""
    async with session_factory() as session:
        alert = await _insert_alert(session)
        delivery = AlertDelivery(
            alert_id=int(alert.id),
            channel="telegram",
            status="sent",
            telegram_message_id=None,
        )
        session.add(delivery)
        await session.flush()
        session.add(
            AlertExplanation(
                pattern_trigger_id=int(alert.id),
                alert_delivery_id=int(delivery.id),
                status="pending",
                cache_key="cache",
                prompt_hash="hash",
                prompt_context_json={},
                created_at=NOW,
            )
        )
        await session.commit()

    anthropic = FakeAnthropicClient()
    client = FakeTelegramClient()
    sender = TelegramAlertSender(client, "42", session_factory=session_factory)
    service = ExplanationService(
        client=anthropic,
        telegram_sender=sender,
        config=ExplanationServiceConfig(enabled=True, api_key_configured=True),
        now=lambda: NOW,
    )
    worker = ExplanationWorker(
        session_factory,
        service,
        poll_seconds=30,
        running_stale_minutes=10,
        now=lambda: NOW,
    )

    assert await worker.run_once() == 1

    async with session_factory() as session:
        explanation = await session.scalar(select(AlertExplanation))

    assert explanation is not None
    assert explanation.status == "skipped_no_base_message"
    assert explanation.error_message == "base telegram message id missing"
    assert anthropic.calls == 0
    assert client.messages == []
