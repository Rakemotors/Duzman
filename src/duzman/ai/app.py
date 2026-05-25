# src/duzman/ai/app.py
# Composition root for the optional Day 8 AI explanation worker runtime.
"""Runtime wiring for AI explanation worker components."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from duzman.ai.anthropic_client import AnthropicClient
from duzman.ai.explanation_service import ExplanationService, ExplanationServiceConfig
from duzman.ai.explanation_worker import ExplanationWorker, build_explanation_worker
from duzman.db.session_async import (
    build_async_database_session_components,
    build_async_database_url,
)
from duzman.settings import Settings
from duzman.telegram.sender import TelegramAlertSender, TelegramBotClient

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AiWorkerComponents:
    """Concrete runtime dependencies for the AI explanation worker."""

    async_engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    explanation_service: ExplanationService
    worker: ExplanationWorker
    telegram_sender: TelegramAlertSender


def build_components_from_settings(settings: Settings) -> AiWorkerComponents:
    """Build AI explanation worker components from process settings.

    The sync `DATABASE_URL` remains unchanged for existing sync code. This
    composition root derives an async SQLAlchemy URL only for the day-8 worker.
    """
    telegram_bot_token = settings.telegram_bot_token.get_secret_value()
    anthropic_api_key = settings.anthropic_api_key.get_secret_value()

    async_database = build_async_database_session_components(settings)
    async_engine = async_database.async_engine
    session_factory = async_database.session_factory

    if not telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN must be configured for AI explanations")
    if not settings.telegram_chat_id_alerts:
        raise ValueError("TELEGRAM_CHAT_ID_ALERTS must be configured for AI explanations")

    telegram_client = TelegramBotClient(telegram_bot_token)
    telegram_sender = TelegramAlertSender(
        telegram_client,
        settings.telegram_chat_id_alerts,
        session_factory=session_factory,
    )
    anthropic_client = AnthropicClient(
        anthropic_api_key,
        fallback_model=settings.ai_explanation_fallback_model,
        retry_max=settings.ai_explanation_retry_max,
    )
    config = ExplanationServiceConfig.from_settings(settings)
    explanation_service = ExplanationService(
        client=anthropic_client,
        telegram_sender=telegram_sender,
        config=config,
    )
    worker = build_explanation_worker(
        session_factory,
        explanation_service,
        poll_seconds=settings.ai_explanation_worker_poll_seconds,
        running_stale_minutes=settings.ai_explanation_running_stale_minutes,
    )
    LOGGER.debug("ai_worker_components_built")
    return AiWorkerComponents(
        async_engine=async_engine,
        session_factory=session_factory,
        explanation_service=explanation_service,
        worker=worker,
        telegram_sender=telegram_sender,
    )


async def dispose_components(components: AiWorkerComponents) -> None:
    """Dispose resources owned by AI worker components."""
    await components.async_engine.dispose()


def _build_async_database_url(sync_url: str) -> str:
    """Return an asyncpg SQLAlchemy URL derived from a supported sync URL."""
    return build_async_database_url(sync_url)
