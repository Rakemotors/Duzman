# src/duzman/dispatch/harness/__init__.py
# Dispatch harness package. Exports deterministic offline fakes and the batch
# orchestrator for exercising dispatch composition without runtime wiring.
"""Deterministic offline dispatch harness package."""

from duzman.dispatch.harness.fake_ai import FakeAIWorker
from duzman.dispatch.harness.fake_persistence import FakePersistence
from duzman.dispatch.harness.fake_sender import FakeTelegramSender
from duzman.dispatch.harness.orchestrator import (
    DispatchHarness,
    HarnessDispatchResult,
    run_dispatch_harness,
)

__all__ = [
    "DispatchHarness",
    "FakeAIWorker",
    "FakePersistence",
    "FakeTelegramSender",
    "HarnessDispatchResult",
    "run_dispatch_harness",
]
