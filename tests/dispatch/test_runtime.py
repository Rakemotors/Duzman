# tests/dispatch/test_runtime.py
# Dispatch runtime service tests. Verifies idempotent reservation, fake sender
# and AI composition, and safe failure handling without network dependencies.
"""Tests for runtime dispatch composition."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.dispatch.ai_worker import DispatchAIExplanationResult
from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.persistence.repository import (
    DISPATCH_DELIVERY_DIALECT_SQLITE,
    DispatchDeliveryRepository,
)
from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SENT,
    TELEGRAM_CHANNEL,
)
from duzman.dispatch.runtime import DispatchRuntimeService
from duzman.dispatch.telegram.result import (
    TELEGRAM_ERROR_API,
    TELEGRAM_STATUS_SENT,
    TelegramSendResult,
)

NOW = datetime(2026, 6, 2, 12, 0, tzinfo=UTC)


class FakeSender:
    """Telegram sender fake for runtime dispatch tests."""

    def __init__(self, *, raise_on_send: bool = False) -> None:
        self.raise_on_send = raise_on_send
        self.calls: list[DispatchEvent] = []

    async def send(self, event: DispatchEvent) -> TelegramSendResult:
        """Record one event and return a deterministic send result."""
        self.calls.append(event)
        if self.raise_on_send:
            raise RuntimeError("telegram transport failed")
        return TelegramSendResult(
            status=TELEGRAM_STATUS_SENT,
            telegram_message_id=event.pattern_trigger_id * 100,
            error_reason=None,
            attempts=1,
        )


class FakeAIWorker:
    """AI worker fake for runtime dispatch tests."""

    def __init__(self, *, raise_on_explain: bool = False) -> None:
        self.raise_on_explain = raise_on_explain
        self.calls: list[DispatchEvent] = []

    async def explain(self, event: DispatchEvent) -> DispatchAIExplanationResult:
        """Record one event and return or raise a deterministic AI result."""
        self.calls.append(event)
        if self.raise_on_explain:
            raise RuntimeError("cache store failed")
        return DispatchAIExplanationResult(
            status="completed",
            explanation="fake explanation",
            error_reason=None,
            model="fake-model",
            prompt_hash="hash",
            cache_key="cache",
            prompt_context_json={},
        )


@pytest.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create an in-memory async SQLite schema for dispatch runtime tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await _create_schema(connection)
        await _seed_rows(connection)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_dispatch_performs_no_send_or_ai_calls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Disabled runtime dispatch should not send, explain, or persist rows."""
    sender = FakeSender()
    ai_worker = FakeAIWorker()
    service = _service(session_factory, sender=sender, ai_worker=ai_worker, enabled=False)

    results = await service.dispatch_events([_event()])

    assert results == []
    assert sender.calls == []
    assert ai_worker.calls == []
    assert await _delivery_count(session_factory) == 0


@pytest.mark.asyncio
async def test_enabled_dispatch_sends_and_persists_sent_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Enabled runtime dispatch should reserve, send, finalize, and run AI."""
    sender = FakeSender()
    ai_worker = FakeAIWorker()
    service = _service(session_factory, sender=sender, ai_worker=ai_worker)

    results = await service.dispatch_events([_event()])
    row = await _delivery_row(session_factory, pattern_trigger_id=1)

    assert len(results) == 1
    assert results[0].reservation.persisted is True
    assert results[0].telegram_result is not None
    assert results[0].ai_result is not None
    assert sender.calls == [_event()]
    assert ai_worker.calls == [_event()]
    assert row is not None
    assert row.status == DELIVERY_STATUS_SENT
    assert row.telegram_message_id == 100


@pytest.mark.asyncio
async def test_duplicate_dispatch_does_not_send_again(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """A second dispatch for the same trigger/channel should skip sending."""
    sender = FakeSender()
    service = _service(session_factory, sender=sender)

    first = await service.dispatch_events([_event()])
    second = await service.dispatch_events([_event()])

    assert first[0].reservation.persisted is True
    assert second[0].reservation.persisted is False
    assert sender.calls == [_event()]
    assert await _delivery_count(session_factory) == 1


@pytest.mark.asyncio
async def test_sender_exception_finalizes_failed_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Sender exceptions should become failed delivery rows without raising."""
    sender = FakeSender(raise_on_send=True)
    service = _service(session_factory, sender=sender)

    results = await service.dispatch_events([_event()])
    row = await _delivery_row(session_factory, pattern_trigger_id=1)

    assert results[0].telegram_result is not None
    assert results[0].telegram_result.status == "failed"
    assert results[0].telegram_result.error_reason == TELEGRAM_ERROR_API
    assert row is not None
    assert row.status == DELIVERY_STATUS_FAILED
    assert row.error_message == TELEGRAM_ERROR_API


@pytest.mark.asyncio
async def test_ai_failure_does_not_rollback_telegram_delivery(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """AI/cache failures should be contained after Telegram persistence."""
    sender = FakeSender()
    ai_worker = FakeAIWorker(raise_on_explain=True)
    service = _service(session_factory, sender=sender, ai_worker=ai_worker)

    results = await service.dispatch_events([_event()])
    row = await _delivery_row(session_factory, pattern_trigger_id=1)

    assert results[0].telegram_result is not None
    assert results[0].telegram_result.status == DELIVERY_STATUS_SENT
    assert results[0].ai_result is None
    assert row is not None
    assert row.status == DELIVERY_STATUS_SENT


def _event(pattern_trigger_id: int = 1) -> DispatchEvent:
    """Build a deterministic dispatch event for a seeded trigger."""
    return DispatchEvent(
        pattern_trigger_id=pattern_trigger_id,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={"gate_decision": "ALLOW", "RSI_4h": 70.0},
    )


def _service(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    sender: FakeSender,
    ai_worker: FakeAIWorker | None = None,
    enabled: bool = True,
) -> DispatchRuntimeService:
    """Build a dispatch runtime service configured for SQLite tests."""
    return DispatchRuntimeService(
        session_factory=session_factory,
        sender=sender,
        ai_worker=ai_worker,
        enabled=enabled,
        dialect=DISPATCH_DELIVERY_DIALECT_SQLITE,
    )


async def _delivery_row(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    pattern_trigger_id: int,
):
    """Return a persisted Telegram delivery row through the real repository."""
    async with session_factory() as session:
        return await DispatchDeliveryRepository(
            session,
            dialect=DISPATCH_DELIVERY_DIALECT_SQLITE,
        ).find_existing(
            pattern_trigger_id=pattern_trigger_id,
            channel=TELEGRAM_CHANNEL,
        )


async def _delivery_count(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Return the number of persisted Telegram delivery rows."""
    count = 0
    for pattern_trigger_id in (1, 2, 3):
        if await _delivery_row(
            session_factory,
            pattern_trigger_id=pattern_trigger_id,
        ):
            count += 1
    return count


async def _create_schema(connection: Any) -> None:
    """Create the minimal tables needed by dispatch runtime tests."""
    await connection.exec_driver_sql(
        """
        CREATE TABLE assets (
            symbol VARCHAR(10) PRIMARY KEY,
            name VARCHAR(50),
            enabled BOOLEAN DEFAULT 1,
            added_at DATETIME
        )
        """
    )
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
            user_feedback_at DATETIME,
            FOREIGN KEY(asset) REFERENCES assets(symbol)
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
            UNIQUE(alert_id, channel),
            FOREIGN KEY(alert_id) REFERENCES pattern_triggers(id) ON DELETE CASCADE
        )
        """
    )


async def _seed_rows(connection: Any) -> None:
    """Seed BTC and three pattern triggers for runtime dispatch tests."""
    await connection.exec_driver_sql(
        "INSERT INTO assets (symbol, name, enabled, added_at) VALUES ('BTC', 'Bitcoin', 1, ?)",
        (NOW,),
    )
    for trigger_id in (1, 2, 3):
        await connection.exec_driver_sql(
            """
            INSERT INTO pattern_triggers
                (id, ts, pattern_name, asset, severity, conditions_snapshot, alert_sent)
            VALUES (?, ?, 'test_pattern', 'BTC', 'WARNING', '{"gate_decision": "ALLOW"}', 0)
            """,
            (trigger_id, NOW),
        )
