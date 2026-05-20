from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.ai.anthropic_client import AnthropicCallError, ExplanationResult
from duzman.ai.explanation_service import ExplanationService, ExplanationServiceConfig
from duzman.db.models import AlertExplanation, PatternTrigger

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
    assert sender.sent == [(10, "ai text")]


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
    assert sender.sent == [(10, "cached text")]


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


async def _seed_pending(session: AsyncSession) -> AlertExplanation:
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
    explanation = AlertExplanation(
        pattern_trigger_id=int(trigger.id),
        alert_delivery_id=10,
        status="pending",
        cache_key="cache",
        prompt_hash="pending",
        prompt_context_json={},
        created_at=NOW,
    )
    session.add(explanation)
    await session.flush()
    return explanation


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
