# tests/dispatch/test_ai_worker.py
# Dispatch AI explanation worker tests. Verifies deterministic provider
# injection, bounded results, and cache behavior without network dependencies.
"""Tests for the dispatch-facing AI explanation worker."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from duzman.dispatch.ai_worker import (
    DISPATCH_EXPLANATION_RETRYABLE_TERMINAL_STATUSES,
    DISPATCH_EXPLANATION_STATUS_COMPLETED,
    DISPATCH_EXPLANATION_STATUS_FAILED,
    DISPATCH_EXPLANATION_STATUS_REUSED_CACHE,
    DISPATCH_EXPLANATION_STATUS_SKIPPED_DISABLED,
    CachedDispatchExplanation,
    DispatchAIExplanationWorker,
    DispatchExplanationProviderError,
    DispatchExplanationRequest,
    DispatchGeneratedExplanation,
    build_dispatch_explanation_request,
)
from duzman.dispatch.contract import DispatchEvent

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


class FakeGenerator:
    """Injected explanation provider test double."""

    def __init__(
        self,
        result: DispatchGeneratedExplanation | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or DispatchGeneratedExplanation(
            text="dispatch explanation",
            model="fake-model",
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        )
        self.error = error
        self.requests: list[DispatchExplanationRequest] = []

    async def generate(
        self,
        request: DispatchExplanationRequest,
    ) -> DispatchGeneratedExplanation:
        """Return or raise the scripted provider outcome."""
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return self.result


class FakeCache:
    """Injected cache test double."""

    def __init__(self) -> None:
        self.values: dict[str, CachedDispatchExplanation] = {}
        self.get_calls: list[str] = []
        self.store_calls: list[tuple[DispatchExplanationRequest, CachedDispatchExplanation]] = []

    async def get(self, cache_key: str) -> CachedDispatchExplanation | None:
        """Return a cached value by key when present."""
        self.get_calls.append(cache_key)
        return self.values.get(cache_key)

    async def store(
        self,
        request: DispatchExplanationRequest,
        explanation: CachedDispatchExplanation,
    ) -> None:
        """Store a cached value and record the write."""
        self.store_calls.append((request, explanation))
        self.values[request.cache_key] = explanation


@pytest.mark.asyncio
async def test_successful_explanation_generation() -> None:
    """The worker should call the injected provider and return completed metadata."""
    generator = FakeGenerator()
    worker = DispatchAIExplanationWorker(generator=generator, enabled=True)

    result = await worker.explain(_event())

    assert result.status == DISPATCH_EXPLANATION_STATUS_COMPLETED
    assert result.explanation == "dispatch explanation"
    assert result.error_reason is None
    assert result.model == "fake-model"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 20
    assert result.total_tokens == 30
    assert result.prompt_hash is not None
    assert result.cache_key is not None
    assert result.prompt_context_json is not None
    assert result.prompt_context_json["asset"] == "BTC"
    assert len(generator.requests) == 1


@pytest.mark.asyncio
async def test_provider_failure_maps_to_safe_failed_result() -> None:
    """Provider errors should not leak exception messages into result metadata."""
    generator = FakeGenerator(error=DispatchExplanationProviderError("provider_timeout"))
    worker = DispatchAIExplanationWorker(generator=generator, enabled=True)

    result = await worker.explain(_event())

    assert result.status == DISPATCH_EXPLANATION_STATUS_FAILED
    assert result.explanation is None
    assert result.error_reason == "provider_timeout"
    assert result.prompt_hash is not None
    assert len(generator.requests) == 1


@pytest.mark.asyncio
async def test_untyped_provider_failure_uses_exception_class_name() -> None:
    """Generic provider failures should map to a bounded class-name reason."""
    generator = FakeGenerator(error=RuntimeError("raw provider detail"))
    worker = DispatchAIExplanationWorker(generator=generator, enabled=True)

    result = await worker.explain(_event())

    assert result.status == DISPATCH_EXPLANATION_STATUS_FAILED
    assert result.error_reason == "RuntimeError"


@pytest.mark.asyncio
async def test_disabled_worker_skips_without_provider_or_cache_calls() -> None:
    """Disabled workers should return skipped-disabled without external calls."""
    generator = FakeGenerator()
    cache = FakeCache()
    worker = DispatchAIExplanationWorker(generator=generator, enabled=False, cache=cache)

    result = await worker.explain(_event())

    assert result.status == DISPATCH_EXPLANATION_STATUS_SKIPPED_DISABLED
    assert result.explanation is None
    assert result.error_reason == "ai_explanations_disabled"
    assert result.prompt_hash is None
    assert generator.requests == []
    assert cache.get_calls == []
    assert cache.store_calls == []


@pytest.mark.asyncio
async def test_empty_provider_text_fails_without_cache_store() -> None:
    """Blank provider output should become a failed result and not be cached."""
    generator = FakeGenerator(result=DispatchGeneratedExplanation(text="  "))
    cache = FakeCache()
    worker = DispatchAIExplanationWorker(generator=generator, enabled=True, cache=cache)

    result = await worker.explain(_event())

    assert result.status == DISPATCH_EXPLANATION_STATUS_FAILED
    assert result.error_reason == "empty_explanation"
    assert len(generator.requests) == 1
    assert cache.store_calls == []


@pytest.mark.asyncio
async def test_cache_hit_avoids_duplicate_provider_call() -> None:
    """Existing cached explanations should avoid external generation."""
    event = _event()
    request = build_dispatch_explanation_request(event)
    cache = FakeCache()
    cache.values[request.cache_key] = CachedDispatchExplanation(
        text="cached explanation",
        model="cached-model",
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
    )
    generator = FakeGenerator()
    worker = DispatchAIExplanationWorker(generator=generator, enabled=True, cache=cache)

    result = await worker.explain(event)

    assert result.status == DISPATCH_EXPLANATION_STATUS_REUSED_CACHE
    assert result.explanation == "cached explanation"
    assert result.model == "cached-model"
    assert result.total_tokens == 3
    assert generator.requests == []
    assert cache.get_calls == [request.cache_key]


@pytest.mark.asyncio
async def test_completed_result_stores_cache_for_future_duplicates() -> None:
    """Completed provider results should be cached under the deterministic key."""
    cache = FakeCache()
    generator = FakeGenerator()
    worker = DispatchAIExplanationWorker(generator=generator, enabled=True, cache=cache)

    first = await worker.explain(_event())
    second = await worker.explain(_event())

    assert first.status == DISPATCH_EXPLANATION_STATUS_COMPLETED
    assert second.status == DISPATCH_EXPLANATION_STATUS_REUSED_CACHE
    assert second.explanation == first.explanation
    assert len(generator.requests) == 1
    assert len(cache.store_calls) == 1


def test_request_metadata_is_deterministic() -> None:
    """Prompt metadata should be stable for identical dispatch events."""
    first = build_dispatch_explanation_request(_event())
    second = build_dispatch_explanation_request(_event())

    assert first.prompt_hash == second.prompt_hash
    assert first.cache_key == second.cache_key
    assert first.context_json == second.context_json
    assert "RSI" in first.user


def test_request_json_context_normalizes_non_json_scalars() -> None:
    """Prompt context should normalize Decimal condition values for JSON storage."""
    request = build_dispatch_explanation_request(
        _event(conditions_snapshot={"gate_decision": "ALLOW", "RSI": Decimal("27.3")})
    )

    assert request.context_json["matched_conditions"]["RSI"] == "27.3"


def test_retryable_statuses_match_existing_ai_semantics() -> None:
    """Dispatch-facing constants should preserve the Day 8 retryable taxonomy."""
    assert DISPATCH_EXPLANATION_RETRYABLE_TERMINAL_STATUSES == frozenset(
        {"failed", "failed_stale", "skipped_cost_cap"}
    )


def _event(
    *,
    conditions_snapshot: dict[str, object] | None = None,
) -> DispatchEvent:
    """Build one valid dispatch event for worker tests."""
    return DispatchEvent(
        pattern_trigger_id=1,
        asset="BTC",
        pattern_name="RSI_oversold_4h",
        severity="medium",
        ts=NOW,
        conditions_snapshot=conditions_snapshot
        if conditions_snapshot is not None
        else {"gate_decision": "ALLOW", "RSI": 27.3},
    )
