# src/duzman/dispatch/ai_worker.py
# Dispatch AI explanation worker. Builds deterministic dispatch prompts and
# calls injected explanation providers without runtime or settings wiring.
"""Inert dispatch-facing AI explanation worker."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from duzman.ai.prompt_builder import SYSTEM_PROMPT
from duzman.dispatch.contract import DispatchEvent

DISPATCH_EXPLANATION_STATUS_COMPLETED = "completed"
DISPATCH_EXPLANATION_STATUS_FAILED = "failed"
DISPATCH_EXPLANATION_STATUS_SKIPPED_DISABLED = "skipped_disabled"
DISPATCH_EXPLANATION_STATUS_REUSED_CACHE = "reused_cache"
DISPATCH_EXPLANATION_STATUSES = frozenset(
    [
        DISPATCH_EXPLANATION_STATUS_COMPLETED,
        DISPATCH_EXPLANATION_STATUS_FAILED,
        DISPATCH_EXPLANATION_STATUS_SKIPPED_DISABLED,
        DISPATCH_EXPLANATION_STATUS_REUSED_CACHE,
    ]
)
DISPATCH_EXPLANATION_RETRYABLE_TERMINAL_STATUSES = frozenset(
    {"failed", "failed_stale", "skipped_cost_cap"}
)

ERROR_REASON_DISABLED = "ai_explanations_disabled"
ERROR_REASON_EMPTY_EXPLANATION = "empty_explanation"


@dataclass(frozen=True)
class DispatchExplanationRequest:
    """Provider request for generating one dispatch explanation."""

    event: DispatchEvent
    system: str
    user: str
    prompt_hash: str
    cache_key: str
    context_json: dict[str, Any]


@dataclass(frozen=True)
class DispatchGeneratedExplanation:
    """Normalized explanation text returned by an injected provider."""

    text: str
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class CachedDispatchExplanation:
    """Cached explanation payload for duplicate dispatch explanation requests."""

    text: str
    model: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class DispatchAIExplanationResult:
    """Bounded result returned by the dispatch-facing AI worker."""

    status: str
    explanation: str | None
    error_reason: str | None
    model: str | None
    prompt_hash: str | None
    cache_key: str | None
    prompt_context_json: dict[str, Any] | None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        """Validate bounded dispatch AI explanation result values.

        Raises:
            ValueError: If result fields are inconsistent with the status.
        """
        if self.status not in DISPATCH_EXPLANATION_STATUSES:
            raise ValueError("status must be one of the dispatch explanation statuses")
        if self.status in {
            DISPATCH_EXPLANATION_STATUS_COMPLETED,
            DISPATCH_EXPLANATION_STATUS_REUSED_CACHE,
        }:
            if self.explanation is None or not self.explanation.strip():
                raise ValueError("explanation must be present for successful statuses")
            if self.error_reason is not None:
                raise ValueError("error_reason must be None for successful statuses")
            return
        if self.explanation is not None:
            raise ValueError("explanation must be None for failed or skipped statuses")
        if self.error_reason is None or not self.error_reason.strip():
            raise ValueError("error_reason must be present for failed or skipped statuses")


class DispatchExplanationProviderError(RuntimeError):
    """Safe provider failure with a bounded reason string."""

    def __init__(self, reason: str) -> None:
        """Create a provider error with a caller-controlled safe reason."""
        super().__init__(reason)
        self.reason = reason


class DispatchExplanationGenerator(Protocol):
    """Provider capability required by the dispatch AI worker."""

    async def generate(
        self,
        request: DispatchExplanationRequest,
    ) -> DispatchGeneratedExplanation:
        """Generate one explanation for a dispatch event."""


class DispatchExplanationCache(Protocol):
    """Cache capability used to avoid duplicate provider calls."""

    async def get(self, cache_key: str) -> CachedDispatchExplanation | None:
        """Return cached explanation data for a cache key when present."""

    async def store(
        self,
        request: DispatchExplanationRequest,
        explanation: CachedDispatchExplanation,
    ) -> None:
        """Store a completed explanation for future duplicate requests."""


@dataclass
class DispatchAIExplanationWorker:
    """Generate dispatch explanations through injected provider dependencies."""

    generator: DispatchExplanationGenerator
    enabled: bool = False
    cache: DispatchExplanationCache | None = None
    max_input_chars: int = 6000

    async def explain(self, event: DispatchEvent) -> DispatchAIExplanationResult:
        """Generate or reuse an explanation for one dispatch event.

        Returns:
            A bounded result. Provider failures are mapped to `failed`; disabled
            workers return `skipped_disabled` without provider or cache calls.
        """
        if not self.enabled:
            return DispatchAIExplanationResult(
                status=DISPATCH_EXPLANATION_STATUS_SKIPPED_DISABLED,
                explanation=None,
                error_reason=ERROR_REASON_DISABLED,
                model=None,
                prompt_hash=None,
                cache_key=None,
                prompt_context_json=None,
            )

        request = build_dispatch_explanation_request(
            event,
            max_input_chars=self.max_input_chars,
        )

        if self.cache is not None:
            cached = await self.cache.get(request.cache_key)
            if cached is not None:
                return _result_from_cached(request, cached)

        try:
            generated = await self.generator.generate(request)
        except DispatchExplanationProviderError as exc:
            return _failed_result(request, exc.reason)
        except Exception as exc:
            return _failed_result(request, exc.__class__.__name__)

        if not generated.text.strip():
            return _failed_result(request, ERROR_REASON_EMPTY_EXPLANATION)

        completed = _result_from_generated(request, generated)
        if self.cache is not None:
            await self.cache.store(
                request,
                CachedDispatchExplanation(
                    text=generated.text,
                    model=generated.model,
                    prompt_tokens=generated.prompt_tokens,
                    completion_tokens=generated.completion_tokens,
                    total_tokens=generated.total_tokens,
                ),
            )
        return completed


def build_dispatch_explanation_request(
    event: DispatchEvent,
    *,
    max_input_chars: int = 6000,
) -> DispatchExplanationRequest:
    """Build deterministic provider input from one dispatch event."""
    context = _context(event)
    context = _truncate_context(context, max_input_chars=max_input_chars)
    user = _render_user(context)
    prompt_hash = _sha256(SYSTEM_PROMPT + user)
    return DispatchExplanationRequest(
        event=event,
        system=SYSTEM_PROMPT,
        user=user,
        prompt_hash=prompt_hash,
        cache_key=_cache_key(context),
        context_json=context,
    )


def _result_from_generated(
    request: DispatchExplanationRequest,
    generated: DispatchGeneratedExplanation,
) -> DispatchAIExplanationResult:
    """Map provider output into a completed dispatch result."""
    return DispatchAIExplanationResult(
        status=DISPATCH_EXPLANATION_STATUS_COMPLETED,
        explanation=generated.text,
        error_reason=None,
        model=generated.model,
        prompt_hash=request.prompt_hash,
        cache_key=request.cache_key,
        prompt_context_json=request.context_json,
        prompt_tokens=generated.prompt_tokens,
        completion_tokens=generated.completion_tokens,
        total_tokens=generated.total_tokens,
    )


def _result_from_cached(
    request: DispatchExplanationRequest,
    cached: CachedDispatchExplanation,
) -> DispatchAIExplanationResult:
    """Map cached explanation data into a reused-cache dispatch result."""
    return DispatchAIExplanationResult(
        status=DISPATCH_EXPLANATION_STATUS_REUSED_CACHE,
        explanation=cached.text,
        error_reason=None,
        model=cached.model,
        prompt_hash=request.prompt_hash,
        cache_key=request.cache_key,
        prompt_context_json=request.context_json,
        prompt_tokens=cached.prompt_tokens,
        completion_tokens=cached.completion_tokens,
        total_tokens=cached.total_tokens,
    )


def _failed_result(
    request: DispatchExplanationRequest,
    reason: str,
) -> DispatchAIExplanationResult:
    """Return a failed result with sanitized provider error metadata."""
    return DispatchAIExplanationResult(
        status=DISPATCH_EXPLANATION_STATUS_FAILED,
        explanation=None,
        error_reason=reason,
        model=None,
        prompt_hash=request.prompt_hash,
        cache_key=request.cache_key,
        prompt_context_json=request.context_json,
    )


def _context(event: DispatchEvent) -> dict[str, Any]:
    """Return normalized dispatch prompt context without raw payload fields."""
    conditions_snapshot = event.conditions_snapshot or {}
    matched_conditions = {
        str(key): _json_safe(value)
        for key, value in sorted(conditions_snapshot.items())
        if key != "gate_decision"
    }
    return {
        "pattern_trigger_id": event.pattern_trigger_id,
        "asset": event.asset,
        "pattern_name": event.pattern_name,
        "severity": event.severity,
        "ts": event.ts.isoformat(),
        "gate_decision": str(conditions_snapshot.get("gate_decision", "UNKNOWN")),
        "matched_conditions": matched_conditions,
    }


def _truncate_context(context: dict[str, Any], *, max_input_chars: int) -> dict[str, Any]:
    """Trim matched conditions deterministically until prompt input fits."""
    trimmed = dict(context)
    trimmed["matched_conditions"] = dict(context["matched_conditions"])
    while len(_render_user(trimmed)) > max_input_chars and trimmed["matched_conditions"]:
        first_key = sorted(trimmed["matched_conditions"])[0]
        del trimmed["matched_conditions"][first_key]
    return trimmed


def _render_user(context: Mapping[str, Any]) -> str:
    """Render deterministic dispatch explanation input text."""
    lines = [
        f"Dispatch id: {context['pattern_trigger_id']}",
        f"Актив: {context['asset']}",
        f"Паттерн: {context['pattern_name']}",
        f"Severity: {context['severity']}",
        f"Trigger time: {context['ts']}",
        f"Gate decision: {context['gate_decision']}",
        "Сработавшие условия:",
    ]
    lines.extend(_bullet_lines(context["matched_conditions"]))
    return "\n".join(lines)


def _bullet_lines(values: Mapping[str, Any]) -> list[str]:
    """Render a mapping as deterministic prompt bullets."""
    if not values:
        return ["- недостаточно данных"]
    return [f"- {key}: {value}" for key, value in sorted(values.items())]


def _cache_key(context: Mapping[str, Any]) -> str:
    """Return a dispatch explanation cache key matching day-8 reason semantics."""
    reason = "|".join(sorted(str(key) for key in context["matched_conditions"]))
    return _sha256(
        f"{context['asset']}|{context['pattern_name']}|"
        f"{context['severity']}|{context['gate_decision']}|{reason}"
    )


def _sha256(value: str) -> str:
    """Return a hex SHA-256 digest."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:64]


def _json_safe(value: Any) -> Any:
    """Convert common non-JSON scalar values into safe prompt values."""
    if isinstance(value, Decimal):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value
