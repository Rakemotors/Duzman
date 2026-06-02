# tests/dispatch/harness/test_orchestrator.py
# Dispatch harness orchestrator tests. Verifies deterministic fake sender/AI
# composition with real in-memory dispatch delivery persistence.
"""Tests for dispatch harness orchestration."""

from __future__ import annotations

from datetime import datetime

import pytest

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.harness import DispatchHarness, run_dispatch_harness
from duzman.dispatch.harness.fake_ai import FakeAIWorker
from duzman.dispatch.harness.fake_persistence import FakePersistence
from duzman.dispatch.harness.fake_sender import FakeTelegramSender
from duzman.dispatch.persistence.row import (
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SENT,
    DELIVERY_STATUS_SKIPPED_DISABLED,
    TELEGRAM_CHANNEL,
)
from duzman.dispatch.telegram.result import (
    TELEGRAM_ERROR_TIMEOUT,
    TELEGRAM_STATUS_FAILED,
    TELEGRAM_STATUS_SKIPPED_DISABLED,
    TelegramSendResult,
)
from tests.dispatch.harness.conftest import build_event


@pytest.mark.asyncio
async def test_sent_event_persists_row(
    harness: DispatchHarness,
    event: DispatchEvent,
    now: datetime,
) -> None:
    """A sent Telegram result should persist a sent delivery row."""
    results = await run_dispatch_harness(harness, [event], now)

    row = await _find_delivery(harness.persistence, event.pattern_trigger_id)

    assert len(results) == 1
    assert results[0].record_result.persisted is True
    assert row is not None
    assert row.status == DELIVERY_STATUS_SENT
    assert row.telegram_message_id == 100
    assert row.sent_at == now


@pytest.mark.asyncio
async def test_failed_event_records_failed_row(
    fake_persistence: FakePersistence,
    ai_worker: FakeAIWorker,
    event: DispatchEvent,
    now: datetime,
) -> None:
    """A failed Telegram result should persist a failed delivery row."""
    sender = FakeTelegramSender(
        outcomes={
            1: TelegramSendResult(
                status=TELEGRAM_STATUS_FAILED,
                telegram_message_id=None,
                error_reason=TELEGRAM_ERROR_TIMEOUT,
                attempts=2,
            )
        }
    )
    harness = DispatchHarness(sender=sender, ai_worker=ai_worker, persistence=fake_persistence)

    await run_dispatch_harness(harness, [event], now)

    row = await _find_delivery(fake_persistence, event.pattern_trigger_id)
    assert row is not None
    assert row.status == DELIVERY_STATUS_FAILED
    assert row.telegram_message_id is None
    assert row.sent_at is None
    assert row.error_message == TELEGRAM_ERROR_TIMEOUT


@pytest.mark.asyncio
async def test_skipped_disabled_event_records_skipped_row(
    fake_persistence: FakePersistence,
    ai_worker: FakeAIWorker,
    event: DispatchEvent,
    now: datetime,
) -> None:
    """A skipped-disabled Telegram result should persist a skipped row."""
    sender = FakeTelegramSender(
        outcomes={
            1: TelegramSendResult(
                status=TELEGRAM_STATUS_SKIPPED_DISABLED,
                telegram_message_id=None,
                error_reason=None,
                attempts=0,
            )
        }
    )
    harness = DispatchHarness(sender=sender, ai_worker=ai_worker, persistence=fake_persistence)

    await run_dispatch_harness(harness, [event], now)

    row = await _find_delivery(fake_persistence, event.pattern_trigger_id)
    assert row is not None
    assert row.status == DELIVERY_STATUS_SKIPPED_DISABLED
    assert row.telegram_message_id is None
    assert row.sent_at is None
    assert row.error_message is None


@pytest.mark.asyncio
async def test_duplicate_event_is_idempotent(
    harness: DispatchHarness,
    event: DispatchEvent,
    now: datetime,
) -> None:
    """Duplicate trigger/channel writes should return an existing row result."""
    first, second = await run_dispatch_harness(harness, [event, event], now)

    assert first.record_result.persisted is True
    assert first.record_result.row_id is not None
    assert second.record_result.persisted is False
    assert second.record_result.existing_row_id == first.record_result.row_id


@pytest.mark.asyncio
async def test_multi_event_batch_returns_all_results(
    harness: DispatchHarness,
    now: datetime,
) -> None:
    """A multi-event batch should return one result per input event."""
    events = [build_event(1), build_event(2), build_event(3)]

    results = await run_dispatch_harness(harness, events, now)

    assert [result.event.pattern_trigger_id for result in results] == [1, 2, 3]
    assert [result.telegram_result.telegram_message_id for result in results] == [
        100,
        200,
        300,
    ]
    assert all(result.record_result.persisted for result in results)


@pytest.mark.asyncio
async def test_ai_worker_called_once_per_event(
    harness: DispatchHarness,
    now: datetime,
) -> None:
    """The fake AI worker should be called once for each input event."""
    events = [build_event(1), build_event(2), build_event(3)]

    await run_dispatch_harness(harness, events, now)

    assert harness.ai_worker.calls == events


@pytest.mark.asyncio
async def test_sender_called_once_per_event(
    harness: DispatchHarness,
    now: datetime,
) -> None:
    """The fake sender should be called once for each input event."""
    events = [build_event(1), build_event(2), build_event(3)]

    await run_dispatch_harness(harness, events, now)

    assert harness.sender.calls == events


@pytest.mark.asyncio
async def test_result_carries_explanation(
    fake_persistence: FakePersistence,
    sender: FakeTelegramSender,
    event: DispatchEvent,
    now: datetime,
) -> None:
    """The harness result should expose the fake AI explanation."""
    ai_worker = FakeAIWorker(explanation="deterministic explanation")
    harness = DispatchHarness(sender=sender, ai_worker=ai_worker, persistence=fake_persistence)

    results = await run_dispatch_harness(harness, [event], now)

    assert results[0].explanation == "deterministic explanation"


async def _find_delivery(
    persistence: FakePersistence,
    pattern_trigger_id: int,
):
    """Find one persisted Telegram delivery row through the real repository."""
    async with persistence.session() as session:
        return await persistence.repository(session).find_existing(
            pattern_trigger_id=pattern_trigger_id,
            channel=TELEGRAM_CHANNEL,
        )
