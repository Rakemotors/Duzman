# src/duzman/dispatch/harness/fake_sender.py
# Dispatch harness fake Telegram sender. Records deterministic send calls and
# returns configured TelegramSendResult values by pattern trigger id.
"""Deterministic fake Telegram sender for dispatch harness tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.telegram.result import (
    TELEGRAM_STATUS_SENT,
    TelegramSendResult,
)


@dataclass
class FakeTelegramSender:
    """Record dispatch events and return deterministic Telegram outcomes."""

    outcomes: Mapping[int, TelegramSendResult] = field(default_factory=dict)
    calls: list[DispatchEvent] = field(default_factory=list)

    async def send(self, event: DispatchEvent) -> TelegramSendResult:
        """Record one event and return its configured or default outcome."""
        self.calls.append(event)
        configured = self.outcomes.get(event.pattern_trigger_id)
        if configured is not None:
            return configured
        return TelegramSendResult(
            status=TELEGRAM_STATUS_SENT,
            telegram_message_id=event.pattern_trigger_id * 100,
            error_reason=None,
            attempts=1,
        )
