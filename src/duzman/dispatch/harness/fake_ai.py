# src/duzman/dispatch/harness/fake_ai.py
# Dispatch harness fake AI worker. Records explanation calls without importing
# Anthropic, HTTP clients, or production AI runtime code.
"""Deterministic fake AI worker for dispatch harness tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from duzman.dispatch.contract import DispatchEvent


@dataclass
class FakeAIWorker:
    """Record dispatch events and return a deterministic explanation."""

    explanation: str = "fake explanation"
    calls: list[DispatchEvent] = field(default_factory=list)

    async def explain(self, event: DispatchEvent) -> str:
        """Record one event and return the configured explanation string."""
        self.calls.append(event)
        return self.explanation
