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
    create_async_engine,
)

from duzman.ai.anthropic_client import AnthropicClient
from duzman.ai.explanation_service import ExplanationService, ExplanationServiceConfig
from duzman.ai.explanation_worker import ExplanationWorker, build_explanation_worker
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
    async_url = _build_async_database_url(settings.database_url)
    async_engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN must be configured for AI explanations")
    if not settings.telegram_chat_id_alerts:
        raise ValueError("TELEGRAM_CHAT_ID_ALERTS must be configured for AI explanations")

    telegram_client = TelegramBotClient(settings.telegram_bot_token)
    telegram_sender = TelegramAlertSender(
        telegram_client,
        settings.telegram_chat_id_alerts,
        session_factory=session_factory,
    )
    anthropic_client = AnthropicClient(
        settings.anthropic_api_key,
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
    if not sync_url:
        raise ValueError("DATABASE_URL must be configured for AI explanations")
    if sync_url.startswith("postgresql+asyncpg://"):
        return sync_url
    if sync_url.startswith("postgresql://"):
        return f"postgresql+asyncpg://{sync_url.removeprefix('postgresql://')}"
    if sync_url.startswith("postgres://"):
        return f"postgresql+asyncpg://{sync_url.removeprefix('postgres://')}"
    raise ValueError("DATABASE_URL scheme is not supported for AI explanations")
