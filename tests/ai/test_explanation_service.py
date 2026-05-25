from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.ai.anthropic_client import AnthropicCallError, ExplanationResult
from duzman.ai.explanation_service import (
    ExplanationService,
    ExplanationServiceConfig,
    create_pending_explanation,
)
from duzman.ai.prompt_builder import build_prompt
from duzman.db.models import AlertDelivery, AlertExplanation, PatternTrigger

NOW = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


class FakeAnthropicClient:
    """Explanation client test double."""

    def __init__(
        self,
        result: ExplanationResult | None = None,
        error: AnthropicCallError | None = None,
    ) -> None:
        self.result = result or ExplanationResult("ai text", "model", 1, 2, 3)
        self.error = error
        self.calls = 0

    async def create_message(self, **_: object) -> ExplanationResult:
        """Return or raise the scripted client result."""
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


class FakeTelegramSender:
    """Telegram sender test double."""

    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_explanation(self, alert_delivery_id: int, text: str) -> None:
        """Capture explanation sends."""
        self.sent.append((alert_delivery_id, text))


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Create a minimal async SQLite schema for explanation service tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_tables(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_process_task_completed_path(session: AsyncSession) -> None:
    """Service should complete pending rows and send a Telegram follow-up."""
    explanation = await _seed_pending(session)
    client = FakeAnthropicClient()
    sender = FakeTelegramSender()
    service = _service(client, sender)

    status = await service.process_task(session, int(explanation.id))

    assert status == "completed"
    assert explanation.text == "ai text"
    assert explanation.total_tokens == 3
    assert explanation.alert_delivery_id is not None
    assert sender.sent == [(int(explanation.alert_delivery_id), "ai text")]


@pytest.mark.asyncio
async def test_process_task_failed_path(session: AsyncSession) -> None:
    """Anthropic failures should mark the task failed without sending Telegram."""
    explanation = await _seed_pending(session)
    client = FakeAnthropicClient(error=AnthropicCallError("TimeoutError", retryable=True))
    sender = FakeTelegramSender()
    service = _service(client, sender)

    status = await service.process_task(session, int(explanation.id))

    assert status == "failed"
    assert explanation.error_message == "TimeoutError"
    assert sender.sent == []


@pytest.mark.asyncio
async def test_process_task_reuses_cache(session: AsyncSession) -> None:
    """Cache hits should avoid Anthropic calls and still send the explanation."""
    session.add(
        AlertExplanation(
            pattern_trigger_id=999,
            alert_delivery_id=None,
            status="completed",
            cache_key="cache",
            prompt_hash="old",
            text="cached text",
            created_at=NOW - timedelta(minutes=1),
        )
    )
    explanation = await _seed_pending(session)
    client = FakeAnthropicClient()
    sender = FakeTelegramSender()
    service = _service(client, sender)

    status = await service.process_task(session, int(explanation.id))

    assert status == "reused_cache"
    assert explanation.text == "cached text"
    assert client.calls == 0
    assert explanation.alert_delivery_id is not None
    assert sender.sent == [(int(explanation.alert_delivery_id), "cached text")]


@pytest.mark.asyncio
async def test_process_task_skips_cost_cap(session: AsyncSession) -> None:
    """Reached cost cap should skip Anthropic calls and not send Telegram."""
    session.add(
        AlertExplanation(
            pattern_trigger_id=999,
            alert_delivery_id=None,
            status="completed",
            cache_key="other",
            prompt_hash="old",
            text="old",
            created_at=NOW - timedelta(minutes=1),
        )
    )
    explanation = await _seed_pending(session)
    client = FakeAnthropicClient()
    sender = FakeTelegramSender()
    service = _service(
        client,
        sender,
        config=ExplanationServiceConfig(
            enabled=True,
            api_key_configured=True,
            max_per_hour=1,
            max_per_day=10,
        ),
    )

    status = await service.process_task(session, int(explanation.id))

    assert status == "skipped_cost_cap"
    assert explanation.error_message == "hour cap reached"
    assert client.calls == 0
    assert sender.sent == []


@pytest.mark.asyncio
async def test_process_task_does_not_self_block_after_claim(
    session: AsyncSession,
) -> None:
    """A claimed running task should not count itself before the Anthropic call."""
    explanation = await _seed_pending(session)
    client = FakeAnthropicClient()
    sender = FakeTelegramSender()
    service = _service(
        client,
        sender,
        config=ExplanationServiceConfig(
            enabled=True,
            api_key_configured=True,
            max_per_hour=1,
            max_per_day=1,
        ),
    )

    status = await service.process_task(session, int(explanation.id))

    assert status == "completed"
    assert client.calls == 1
    assert explanation.text == "ai text"
    assert explanation.total_tokens == 3
    assert explanation.alert_delivery_id is not None
    assert sender.sent == [(int(explanation.alert_delivery_id), "ai text")]


@pytest.mark.asyncio
async def test_process_task_skips_missing_base_message_before_anthropic(
    session: AsyncSession,
) -> None:
    """Missing base message ids should skip before cache, budget, or Anthropic."""
    explanation = await _seed_pending(session, telegram_message_id=None)
    client = FakeAnthropicClient()
    sender = FakeTelegramSender()
    service = _service(client, sender)

    status = await service.process_task(session, int(explanation.id))

    assert status == "skipped_no_base_message"
    assert explanation.error_message == "base telegram message id missing"
    assert client.calls == 0
    assert sender.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["failed", "failed_stale", "skipped_cost_cap"])
async def test_create_pending_explanation_requeues_retryable_terminal_row(
    session: AsyncSession,
    status: str,
) -> None:
    """Retryable terminal rows should be reset in place without duplicate inserts."""
    trigger, delivery = await _seed_trigger_and_delivery(session)
    _, stale_delivery = await _seed_trigger_and_delivery(session)
    existing = await _seed_existing_explanation(
        session,
        trigger,
        stale_delivery,
        status=status,
        cache_key="stale-cache",
    )
    original_id = int(existing.id)
    original_created_at = existing.created_at
    expected_prompt = build_prompt(trigger, {}, None, max_input_chars=6000)

    result = await create_pending_explanation(
        session,
        trigger,
        alert_delivery_id=int(delivery.id),
        max_input_chars=6000,
    )

    assert result is existing
    assert int(result.id) == original_id
    assert result.pattern_trigger_id == int(trigger.id)
    assert result.alert_delivery_id == int(delivery.id)
    assert result.alert_delivery_id != int(stale_delivery.id)
    assert result.cache_key == expected_prompt.cache_key
    assert result.cache_key != "stale-cache"
    assert result.created_at == original_created_at
    assert result.status == "pending"
    assert result.started_at is None
    assert result.completed_at is None
    assert result.error_message is None
    assert result.model is None
    assert result.text is None
    assert result.prompt_tokens is None
    assert result.completion_tokens is None
    assert result.total_tokens is None
    assert result.prompt_hash != "old-hash"
    assert result.prompt_context_json
    assert result.prompt_context_json["asset"] == "BTC"
    assert await _explanation_count_for_trigger(session, int(trigger.id)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    [
        "completed",
        "reused_cache",
        "skipped_disabled",
        "skipped_no_base_message",
        "pending",
        "running",
    ],
)
async def test_create_pending_explanation_preserves_non_retryable_existing_row(
    session: AsyncSession,
    status: str,
) -> None:
    """Non-retryable existing rows should remain the idempotency boundary."""
    trigger, delivery = await _seed_trigger_and_delivery(session)
    existing = await _seed_existing_explanation(session, trigger, delivery, status=status)
    snapshot = _explanation_snapshot(existing)

    result = await create_pending_explanation(
        session,
        trigger,
        alert_delivery_id=int(delivery.id),
        max_input_chars=6000,
    )

    assert result is None
    assert _explanation_snapshot(existing) == snapshot
    assert await _explanation_count_for_trigger(session, int(trigger.id)) == 1


@pytest.mark.asyncio
async def test_requeued_failed_row_can_complete_successfully(
    session: AsyncSession,
) -> None:
    """A same-row retry should be processable by the existing pending worker path."""
    trigger, delivery = await _seed_trigger_and_delivery(session)
    existing = await _seed_existing_explanation(session, trigger, delivery, status="failed")
    result = await create_pending_explanation(
        session,
        trigger,
        alert_delivery_id=int(delivery.id),
    )
    assert result is existing

    sender = FakeTelegramSender()
    status = await _service(FakeAnthropicClient(), sender).process_task(session, int(existing.id))

    assert status == "completed"
    assert existing.status == "completed"
    assert existing.text == "ai text"
    assert sender.sent == [(int(delivery.id), "ai text")]
    assert await _explanation_count_for_trigger(session, int(trigger.id)) == 1


@pytest.mark.asyncio
async def test_requeued_skipped_cost_cap_can_skip_again_when_budget_exceeded(
    session: AsyncSession,
) -> None:
    """A cost-cap retry should reuse the row and keep existing budget behavior."""
    trigger, delivery = await _seed_trigger_and_delivery(session)
    existing = await _seed_existing_explanation(
        session,
        trigger,
        delivery,
        status="skipped_cost_cap",
        cache_key="retry-cache",
    )
    session.add(
        AlertExplanation(
            pattern_trigger_id=999,
            alert_delivery_id=None,
            status="completed",
            cache_key="budget-cache",
            prompt_hash="budget-hash",
            text="budget text",
            created_at=NOW - timedelta(minutes=1),
        )
    )
    await session.flush()
    result = await create_pending_explanation(
        session,
        trigger,
        alert_delivery_id=int(delivery.id),
    )
    assert result is existing

    client = FakeAnthropicClient()
    sender = FakeTelegramSender()
    status = await _service(
        client,
        sender,
        config=ExplanationServiceConfig(
            enabled=True,
            api_key_configured=True,
            max_per_hour=1,
            max_per_day=10,
        ),
    ).process_task(session, int(existing.id))

    assert status == "skipped_cost_cap"
    assert existing.error_message == "hour cap reached"
    assert client.calls == 0
    assert sender.sent == []
    assert await _explanation_count_for_trigger(session, int(trigger.id)) == 1


async def _seed_pending(
    session: AsyncSession,
    *,
    telegram_message_id: int | None = 456,
) -> AlertExplanation:
    """Insert one PatternTrigger and pending explanation row."""
    trigger = PatternTrigger(
        ts=NOW,
        pattern_name="RSI_oversold_4h",
        asset="BTC",
        severity="medium",
        conditions_snapshot={"gate_decision": "ALLOW", "RSI": 27.3},
        alert_sent=False,
    )
    session.add(trigger)
    await session.flush()
    delivery = AlertDelivery(
        alert_id=int(trigger.id),
        channel="telegram",
        status="sent",
        telegram_message_id=telegram_message_id,
    )
    session.add(delivery)
    await session.flush()
    explanation = AlertExplanation(
        pattern_trigger_id=int(trigger.id),
        alert_delivery_id=int(delivery.id),
        status="pending",
        cache_key="cache",
        prompt_hash="pending",
        prompt_context_json={},
        created_at=NOW,
    )
    session.add(explanation)
    await session.flush()
    return explanation


async def _seed_trigger_and_delivery(
    session: AsyncSession,
    *,
    telegram_message_id: int | None = 456,
) -> tuple[PatternTrigger, AlertDelivery]:
    """Insert one PatternTrigger and Telegram delivery row."""
    trigger = PatternTrigger(
        ts=NOW,
        pattern_name="RSI_oversold_4h",
        asset="BTC",
        severity="medium",
        conditions_snapshot={"gate_decision": "ALLOW", "RSI": 27.3},
        alert_sent=False,
    )
    session.add(trigger)
    await session.flush()
    delivery = AlertDelivery(
        alert_id=int(trigger.id),
        channel="telegram",
        status="sent",
        telegram_message_id=telegram_message_id,
    )
    session.add(delivery)
    await session.flush()
    return trigger, delivery


async def _seed_existing_explanation(
    session: AsyncSession,
    trigger: PatternTrigger,
    delivery: AlertDelivery,
    *,
    status: str,
    cache_key: str = "existing-cache",
) -> AlertExplanation:
    """Insert an existing explanation row with stale retry metadata."""
    explanation = AlertExplanation(
        pattern_trigger_id=int(trigger.id),
        alert_delivery_id=int(delivery.id),
        status=status,
        model="old-model",
        cache_key=cache_key,
        prompt_hash="old-hash",
        prompt_context_json={"old": True},
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        text="old text",
        error_message="old error",
        created_at=NOW - timedelta(minutes=5),
        started_at=NOW - timedelta(minutes=4),
        completed_at=NOW - timedelta(minutes=3),
    )
    session.add(explanation)
    await session.flush()
    return explanation


def _explanation_snapshot(explanation: AlertExplanation) -> dict[str, object]:
    """Capture fields that must not change for non-retryable rows."""
    return {
        "id": explanation.id,
        "pattern_trigger_id": explanation.pattern_trigger_id,
        "alert_delivery_id": explanation.alert_delivery_id,
        "status": explanation.status,
        "model": explanation.model,
        "cache_key": explanation.cache_key,
        "prompt_hash": explanation.prompt_hash,
        "prompt_context_json": explanation.prompt_context_json,
        "prompt_tokens": explanation.prompt_tokens,
        "completion_tokens": explanation.completion_tokens,
        "total_tokens": explanation.total_tokens,
        "text": explanation.text,
        "error_message": explanation.error_message,
        "created_at": explanation.created_at,
        "started_at": explanation.started_at,
        "completed_at": explanation.completed_at,
    }


async def _explanation_count_for_trigger(session: AsyncSession, trigger_id: int) -> int:
    """Return the number of explanation rows for one pattern trigger."""
    rows = await session.scalars(
        select(AlertExplanation).where(AlertExplanation.pattern_trigger_id == trigger_id)
    )
    return len(list(rows))


def _service(
    client: FakeAnthropicClient,
    sender: FakeTelegramSender,
    *,
    config: ExplanationServiceConfig | None = None,
) -> ExplanationService:
    """Build a deterministic ExplanationService for tests."""
    return ExplanationService(
        client=client,
        telegram_sender=sender,
        config=config
        or ExplanationServiceConfig(
            enabled=True,
            api_key_configured=True,
            cache_window_minutes=15,
        ),
        now=lambda: NOW,
    )


async def _create_tables(connection: Any) -> None:
    """Create minimal service schema."""
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
            created_at DATETIME NOT NULL,
            started_at DATETIME,
            completed_at DATETIME
        )
        """
    )
