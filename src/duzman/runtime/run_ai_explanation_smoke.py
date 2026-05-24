# src/duzman/runtime/run_ai_explanation_smoke.py
# Dev-only smoke harness for processing a Day 8 AI explanation for a B0
# Telegram smoke trigger.
"""Run one AI explanation smoke cycle for an existing B0 trigger."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from duzman.ai.app import (
    AiWorkerComponents,
    build_components_from_settings,
    dispose_components,
)
from duzman.ai.explanation_service import create_pending_explanation
from duzman.db.models import AlertDelivery, AlertExplanation, PatternTrigger
from duzman.logging_config import configure_logging, safe_error_message
from duzman.settings import Settings

LOGGER = logging.getLogger(__name__)
SUCCESS_STATUSES = {"completed", "reused_cache"}


@dataclass(frozen=True)
class AiExplanationSmokeSettings:
    """Settings needed by the AI explanation smoke script."""

    ai_explanations_enabled: bool = False
    anthropic_api_key: str = ""
    ai_explanation_max_per_hour: int = 10
    ai_explanation_max_per_day: int = 50
    ai_explanation_max_input_chars: int = 6000


SettingsProvider = Callable[[], AiExplanationSmokeSettings]
ComponentsBuilder = Callable[[Settings], AiWorkerComponents]


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_provider: SettingsProvider | None = None,
    product_settings_provider: Callable[[], Settings] = Settings,
    components_builder: ComponentsBuilder = build_components_from_settings,
) -> int:
    """Run the AI explanation smoke command and return a process exit code."""
    args = _build_parser().parse_args(list(argv or ()))
    configure_logging()
    return asyncio.run(
        _async_main(
            args,
            settings_provider=settings_provider or _load_smoke_settings,
            product_settings_provider=product_settings_provider,
            components_builder=components_builder,
        )
    )


async def _async_main(
    args: argparse.Namespace,
    *,
    settings_provider: SettingsProvider,
    product_settings_provider: Callable[[], Settings],
    components_builder: ComponentsBuilder,
) -> int:
    """Execute the async AI explanation smoke workflow."""
    components: AiWorkerComponents | None = None
    try:
        smoke_settings = settings_provider()
        validation_error = _validate_settings(smoke_settings)
        if validation_error is not None:
            print(validation_error)
            return 2
        _warn_about_cost_caps(smoke_settings)

        product_settings = product_settings_provider()
        components = components_builder(product_settings)

        async with components.session_factory() as session:
            trigger = await session.get(PatternTrigger, args.trigger_id)
            if trigger is None:
                if args.rollback:
                    print("SMOKE_ROLLBACK_NOOP")
                    return 0
                print("smoke trigger not found")
                return 2
            if trigger.pattern_name != "smoke_b0":
                print("trigger is not a smoke_b0 trigger")
                return 2

            delivery = await _get_telegram_delivery(session, int(trigger.id))
            if delivery is None:
                print("telegram delivery for smoke trigger not found")
                return 2

            explanation = await create_pending_explanation(
                session,
                trigger,
                alert_delivery_id=int(delivery.id),
                max_input_chars=smoke_settings.ai_explanation_max_input_chars,
            )
            await session.commit()
            if explanation is None:
                explanation = await _get_explanation_by_trigger(session, int(trigger.id))
            if explanation is None:
                print("alert explanation was not created")
                return 1
            explanation_id = int(explanation.id)

        await components.worker.run_once()

        async with components.session_factory() as session:
            explanation = await session.get(AlertExplanation, explanation_id)
            if explanation is None:
                print("alert explanation missing after worker")
                return 1
            if explanation.status not in SUCCESS_STATUSES or not explanation.text:
                print(f"AI_EXPLANATION_SMOKE_NOT_DONE status={explanation.status}")
                return 3
            tokens = explanation.total_tokens or 0
            print(
                "AI_EXPLANATION_SMOKE_OK "
                f"alert_explanation_id={explanation_id} tokens={tokens}"
            )
            if args.rollback:
                result = await _rollback_smoke_rows(
                    session,
                    trigger_id=args.trigger_id,
                    delivery_id=explanation.alert_delivery_id,
                    explanation_id=explanation_id,
                )
                await session.commit()
                print(
                    "SMOKE_ROLLBACK_OK "
                    f"pattern_trigger={result.pattern_trigger} "
                    f"alert_delivery={result.alert_delivery} "
                    f"alert_explanation={result.alert_explanation}"
                )
        return 0
    except Exception as exc:
        LOGGER.exception("ai explanation smoke failed: %s", safe_error_message(exc))
        return 1
    finally:
        if components is not None:
            await dispose_components(components)


@dataclass(frozen=True)
class RollbackResult:
    """Result labels for idempotent smoke row rollback."""

    pattern_trigger: str
    alert_delivery: str
    alert_explanation: str


def _build_parser() -> argparse.ArgumentParser:
    """Build the parser for the AI explanation smoke command."""
    parser = argparse.ArgumentParser(
        description="Process one AI explanation for an existing B0 smoke trigger.",
    )
    parser.add_argument("--trigger-id", type=int, required=True)
    parser.add_argument("--rollback", action="store_true")
    return parser


def _load_smoke_settings() -> AiExplanationSmokeSettings:
    """Load smoke settings through the product Settings layer."""
    settings = Settings()
    return AiExplanationSmokeSettings(
        ai_explanations_enabled=settings.ai_explanations_enabled,
        anthropic_api_key=settings.anthropic_api_key.get_secret_value(),
        ai_explanation_max_per_hour=settings.ai_explanation_max_per_hour,
        ai_explanation_max_per_day=settings.ai_explanation_max_per_day,
        ai_explanation_max_input_chars=settings.ai_explanation_max_input_chars,
    )


def _validate_settings(settings: AiExplanationSmokeSettings) -> str | None:
    """Return a safe validation error message or None."""
    if not settings.ai_explanations_enabled:
        return "AI_EXPLANATIONS_ENABLED must be true for B1 smoke"
    if not settings.anthropic_api_key:
        return "missing ANTHROPIC_API_KEY"
    return None


def _warn_about_cost_caps(settings: AiExplanationSmokeSettings) -> None:
    """Log a non-blocking warning when smoke cost caps are above the recommendation."""
    if settings.ai_explanation_max_per_hour > 3 or settings.ai_explanation_max_per_day > 5:
        LOGGER.warning("ai explanation smoke cost caps are above recommended values")


async def _get_telegram_delivery(
    session: AsyncSession,
    trigger_id: int,
) -> AlertDelivery | None:
    """Return the Telegram delivery row for one smoke trigger."""
    return cast(
        AlertDelivery | None,
        await session.scalar(
            select(AlertDelivery).where(
                AlertDelivery.alert_id == trigger_id,
                AlertDelivery.channel == "telegram",
            )
        ),
    )


async def _get_explanation_by_trigger(
    session: AsyncSession,
    trigger_id: int,
) -> AlertExplanation | None:
    """Return the explanation row for one smoke trigger."""
    return cast(
        AlertExplanation | None,
        await session.scalar(
            select(AlertExplanation).where(AlertExplanation.pattern_trigger_id == trigger_id)
        ),
    )


async def _rollback_smoke_rows(
    session: AsyncSession,
    *,
    trigger_id: int,
    delivery_id: int | None,
    explanation_id: int,
) -> RollbackResult:
    """Delete only rows created by the current smoke chain."""
    explanation = await _delete_by_id(session, AlertExplanation, explanation_id)
    delivery = (
        await _delete_by_id(session, AlertDelivery, delivery_id)
        if delivery_id is not None
        else "missing"
    )
    trigger = await _delete_by_id(session, PatternTrigger, trigger_id)
    return RollbackResult(
        pattern_trigger=trigger,
        alert_delivery=delivery,
        alert_explanation=explanation,
    )


async def _delete_by_id(
    session: AsyncSession,
    model: type[PatternTrigger] | type[AlertDelivery] | type[AlertExplanation],
    row_id: int,
) -> str:
    """Delete one ORM row by primary key and return a result label."""
    row = await session.get(model, row_id)
    if row is None:
        return "missing"
    await session.execute(delete(model).where(model.id == row_id))
    return "deleted"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
