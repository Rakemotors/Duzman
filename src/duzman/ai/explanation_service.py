# src/duzman/ai/explanation_service.py
# Orchestrates one AI explanation task from persisted pending row to completed
# text and optional Telegram follow-up delivery.
"""AI explanation task service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.ai.anthropic_client import AnthropicCallError, ExplanationResult
from duzman.ai.cache import lookup_cached_explanation
from duzman.ai.cost_limiter import BudgetStatus, check_budget
from duzman.ai.prompt_builder import PromptBundle, build_prompt
from duzman.db.models import AlertDelivery, AlertExplanation, PatternTrigger
from duzman.settings import Settings

AI_EXPLANATION_RETRYABLE_TERMINAL_STATUSES = frozenset(
    {"failed", "failed_stale", "skipped_cost_cap"}
)


class ExplanationTelegramSender(Protocol):
    """Telegram sender capability required by explanation service."""

    async def send_explanation(self, alert_delivery_id: int, text: str) -> None:
        """Send explanation text as a Telegram follow-up message."""


class ExplanationClient(Protocol):
    """Anthropic client capability required by explanation service."""

    async def create_message(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        timeout: float,  # noqa: ASYNC109 - passed through to client dependency.
    ) -> ExplanationResult:
        """Create one AI explanation message."""


@dataclass(frozen=True)
class ExplanationServiceConfig:
    """Runtime configuration needed to process one explanation task."""

    enabled: bool = False
    api_key_configured: bool = False
    model: str = "claude-sonnet-4-6"
    fallback_model: str = "claude-sonnet-4-5-20250929"
    max_per_hour: int = 10
    max_per_day: int = 50
    timeout_seconds: int = 20
    max_input_chars: int = 6000
    max_output_tokens: int = 500
    cache_window_minutes: int = 15
    retry_max: int = 1

    @classmethod
    def from_settings(cls, settings: Settings) -> ExplanationServiceConfig:
        """Create service config from global project settings."""
        return cls(
            enabled=settings.ai_explanations_enabled,
            api_key_configured=bool(settings.anthropic_api_key.get_secret_value()),
            model=settings.ai_explanation_model,
            fallback_model=settings.ai_explanation_fallback_model,
            max_per_hour=settings.ai_explanation_max_per_hour,
            max_per_day=settings.ai_explanation_max_per_day,
            timeout_seconds=settings.ai_explanation_timeout_seconds,
            max_input_chars=settings.ai_explanation_max_input_chars,
            max_output_tokens=settings.ai_explanation_max_output_tokens,
            cache_window_minutes=settings.ai_explanation_cache_window_minutes,
            retry_max=settings.ai_explanation_retry_max,
        )


class ExplanationService:
    """Process persisted AI explanation tasks."""

    def __init__(
        self,
        *,
        client: ExplanationClient,
        telegram_sender: ExplanationTelegramSender,
        config: ExplanationServiceConfig,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """Create a service with explicit external dependencies."""
        self._client = client
        self._telegram_sender = telegram_sender
        self._config = config
        self._now = now

    async def process_task(self, session: AsyncSession, explanation_id: int) -> str | None:
        """Process one explanation task and return its final status."""
        explanation = await _claim_explanation(session, explanation_id, now=self._now())
        if explanation is None:
            return None

        if not self._config.enabled or not self._config.api_key_configured:
            _finish(
                explanation,
                status="skipped_disabled",
                now=self._now(),
                error_message="AI explanations disabled or API key missing",
            )
            return explanation.status

        if not await _base_delivery_has_message_id(session, explanation):
            _finish(
                explanation,
                status="skipped_no_base_message",
                now=self._now(),
                error_message="base telegram message id missing",
            )
            return explanation.status

        cached = await lookup_cached_explanation(
            session,
            explanation.cache_key,
            window_minutes=self._config.cache_window_minutes,
            now=self._now(),
        )
        if cached is not None:
            _finish(explanation, status="reused_cache", text=cached.text, now=self._now())
            await _send_if_possible(self._telegram_sender, explanation)
            return explanation.status

        budget = await check_budget(
            session,
            max_per_hour=self._config.max_per_hour,
            max_per_day=self._config.max_per_day,
            now=self._now(),
        )
        if budget is not BudgetStatus.OK:
            message = (
                "hour cap reached"
                if budget is BudgetStatus.EXCEEDED_HOUR
                else "day cap reached"
            )
            _finish(
                explanation,
                status="skipped_cost_cap",
                now=self._now(),
                error_message=message,
            )
            return explanation.status

        trigger = await session.get(PatternTrigger, explanation.pattern_trigger_id)
        if trigger is None:
            _finish(
                explanation,
                status="failed",
                now=self._now(),
                error_message="pattern trigger not found",
            )
            return explanation.status

        prompt = build_prompt(
            trigger,
            {},
            None,
            max_input_chars=self._config.max_input_chars,
        )
        explanation.prompt_hash = prompt.prompt_hash
        explanation.prompt_context_json = prompt.context_json
        try:
            result = await self._client.create_message(
                model=self._config.model,
                system=prompt.system,
                user=prompt.user,
                max_tokens=self._config.max_output_tokens,
                timeout=self._config.timeout_seconds,
            )
        except AnthropicCallError as exc:
            _finish(
                explanation,
                status="failed",
                now=self._now(),
                error_message=exc.reason,
            )
            return explanation.status

        _apply_result(explanation, result, now=self._now())
        await _send_if_possible(self._telegram_sender, explanation)
        return explanation.status


async def create_pending_explanation(
    session: AsyncSession,
    pattern_trigger: PatternTrigger,
    *,
    alert_delivery_id: int | None,
    max_input_chars: int = 6000,
) -> AlertExplanation | None:
    """Create a pending explanation task idempotently for one pattern trigger."""
    existing = await session.scalar(
        select(AlertExplanation).where(
            AlertExplanation.pattern_trigger_id == int(pattern_trigger.id)
        )
    )

    if existing is not None:
        if existing.status not in AI_EXPLANATION_RETRYABLE_TERMINAL_STATUSES:
            return None
        prompt = build_prompt(pattern_trigger, {}, None, max_input_chars=max_input_chars)
        _reset_existing_explanation_for_retry(existing, prompt, alert_delivery_id)
        await session.flush()
        return existing

    prompt = build_prompt(pattern_trigger, {}, None, max_input_chars=max_input_chars)
    row = AlertExplanation(
        pattern_trigger_id=int(pattern_trigger.id),
        alert_delivery_id=alert_delivery_id,
        status="pending",
        cache_key=prompt.cache_key,
        prompt_hash=prompt.prompt_hash,
        prompt_context_json=prompt.context_json,
    )
    session.add(row)
    await session.flush()
    return row


def _reset_existing_explanation_for_retry(
    explanation: AlertExplanation,
    prompt: PromptBundle,
    alert_delivery_id: int | None,
) -> None:
    """Reset a retryable terminal row in place to respect the trigger unique index."""
    explanation.status = "pending"
    explanation.alert_delivery_id = alert_delivery_id
    explanation.cache_key = prompt.cache_key
    explanation.started_at = None
    explanation.completed_at = None
    explanation.error_message = None
    explanation.model = None
    explanation.text = None
    explanation.prompt_tokens = None
    explanation.completion_tokens = None
    explanation.total_tokens = None
    explanation.prompt_hash = prompt.prompt_hash
    explanation.prompt_context_json = prompt.context_json


async def _claim_explanation(
    session: AsyncSession,
    explanation_id: int,
    *,
    now: datetime,
) -> AlertExplanation | None:
    """Claim a pending explanation row for processing."""
    statement = (
        select(AlertExplanation)
        .where(
            AlertExplanation.id == explanation_id,
            AlertExplanation.status == "pending",
        )
        .with_for_update(skip_locked=True)
    )
    row = cast(AlertExplanation | None, await session.scalar(statement))
    if row is None:
        return None
    row.status = "running"
    row.started_at = now
    await session.flush()
    return row


async def _base_delivery_has_message_id(
    session: AsyncSession,
    explanation: AlertExplanation,
) -> bool:
    """Return whether the explanation can reply to a base Telegram message."""
    if explanation.alert_delivery_id is None:
        return False
    delivery = await session.get(AlertDelivery, explanation.alert_delivery_id)
    return delivery is not None and delivery.telegram_message_id is not None


def _apply_result(
    explanation: AlertExplanation,
    result: ExplanationResult,
    *,
    now: datetime,
) -> None:
    """Persist a successful Anthropic response on an explanation row."""
    explanation.status = "completed"
    explanation.model = result.model_used
    explanation.prompt_tokens = result.input_tokens
    explanation.completion_tokens = result.output_tokens
    explanation.total_tokens = result.total_tokens
    explanation.text = result.text
    explanation.error_message = None
    explanation.completed_at = now


def _finish(
    explanation: AlertExplanation,
    *,
    status: str,
    now: datetime,
    text: str | None = None,
    error_message: str | None = None,
) -> None:
    """Set a terminal status on an explanation row."""
    explanation.status = status
    explanation.text = text
    explanation.error_message = error_message
    explanation.completed_at = now


async def _send_if_possible(
    telegram_sender: ExplanationTelegramSender,
    explanation: AlertExplanation,
) -> None:
    """Send explanation text when row has a delivery target."""
    if explanation.alert_delivery_id is None or not explanation.text:
        return
    await telegram_sender.send_explanation(int(explanation.alert_delivery_id), explanation.text)
