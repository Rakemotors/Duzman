# src/duzman/dispatch/harness/orchestrator.py
# Dispatch harness orchestrator. Composes deterministic fakes with the real
# persistence repository to test offline dispatch delivery behavior.
"""Offline deterministic dispatch harness orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.harness.fake_ai import FakeAIWorker
from duzman.dispatch.harness.fake_persistence import FakePersistence
from duzman.dispatch.harness.fake_sender import FakeTelegramSender
from duzman.dispatch.persistence.mapping import delivery_row_from_telegram_result
from duzman.dispatch.persistence.row import RecordDeliveryResult
from duzman.dispatch.telegram.result import TelegramSendResult


@dataclass
class DispatchHarness:
    """Container for deterministic dispatch harness dependencies."""

    sender: FakeTelegramSender
    ai_worker: FakeAIWorker
    persistence: FakePersistence


@dataclass(frozen=True)
class HarnessDispatchResult:
    """Full per-event result returned by the deterministic harness."""

    event: DispatchEvent
    telegram_result: TelegramSendResult
    explanation: str
    record_result: RecordDeliveryResult


async def run_dispatch_harness(
    harness: DispatchHarness,
    events: list[DispatchEvent],
    now: datetime,
) -> list[HarnessDispatchResult]:
    """Run deterministic dispatch for events in input order.

    Parameters:
        harness: Fake sender, fake AI worker, and fake persistence context.
        events: Dispatch events processed sequentially in the supplied order.
        now: Timezone-aware timestamp used for successful delivery rows.

    Returns:
        One `HarnessDispatchResult` per input event.
    """
    results: list[HarnessDispatchResult] = []
    async with harness.persistence.session() as session:
        async with session.begin():
            repository = harness.persistence.repository(session)
            for event in events:
                telegram_result = await harness.sender.send(event)
                explanation = await harness.ai_worker.explain(event)
                row = delivery_row_from_telegram_result(
                    event=event,
                    result=telegram_result,
                    now=now,
                )
                record_result = await repository.record_delivery(row)
                results.append(
                    HarnessDispatchResult(
                        event=event,
                        telegram_result=telegram_result,
                        explanation=explanation,
                        record_result=record_result,
                    )
                )
    return results
