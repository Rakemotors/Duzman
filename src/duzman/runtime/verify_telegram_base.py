# src/duzman/runtime/verify_telegram_base.py
# Dev-only smoke harness for verifying Telegram base delivery without the AI
# explanation layer.
"""Verify one Telegram base alert delivery for Day 8 smoke testing."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from duzman.ai.app import _build_async_database_url
from duzman.db.models import AlertDelivery, PatternTrigger
from duzman.logging_config import configure_logging, safe_error_message
from duzman.settings import Settings
from duzman.telegram.poller import TelegramAlertPoller
from duzman.telegram.sender import TelegramAlertSender, TelegramBotClient, TelegramClient

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TelegramBaseSmokeSettings:
    """Settings needed by the Telegram base smoke script."""

    database_url: str = ""
    ai_explanations_enabled: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id_alerts: str = ""


SettingsProvider = Callable[[], TelegramBaseSmokeSettings]


def main(
    argv: Sequence[str] | None = None,
    *,
    settings_provider: SettingsProvider | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    telegram_client_factory: Callable[[str], TelegramClient] | None = None,
) -> int:
    """Run the Telegram base delivery smoke check and return a process exit code."""
    args = _build_parser().parse_args(list(argv or ()))
    configure_logging()
    return asyncio.run(
        _async_main(
            args,
            settings_provider=settings_provider or _load_settings,
            session_factory=session_factory,
            telegram_client_factory=telegram_client_factory,
        )
    )


async def _async_main(
    args: argparse.Namespace,
    *,
    settings_provider: SettingsProvider,
    session_factory: async_sessionmaker[AsyncSession] | None,
    telegram_client_factory: Callable[[str], TelegramClient] | None,
) -> int:
    """Execute the async Telegram base smoke workflow."""
    engine = None
    try:
        settings = settings_provider()
        validation_error = _validate_settings(settings)
        if validation_error is not None:
            print(validation_error)
            return 2

        resolved_factory = session_factory
        if resolved_factory is None:
            async_url = _build_async_database_url(settings.database_url)
            engine = create_async_engine(async_url, echo=False, pool_pre_ping=True)
            resolved_factory = async_sessionmaker(engine, expire_on_commit=False)

        client_factory = telegram_client_factory or TelegramBotClient
        client = client_factory(settings.telegram_bot_token)
        sender = TelegramAlertSender(
            client,
            settings.telegram_chat_id_alerts,
            ai_explanations_enabled=False,
            anthropic_api_key_configured=False,
        )
        poller = TelegramAlertPoller(sender, rate_limit_seconds=0.0)

        async with resolved_factory() as session:
            trigger = PatternTrigger(
                asset="BTC",
                pattern_name="smoke_b0",
                severity="INFO",
                ts=datetime.now(UTC),
                conditions_snapshot={"smoke": True, "gate_decision": "ALLOW"},
                alert_sent=True,
            )
            session.add(trigger)
            await session.flush()
            await poller.run_once(session, limit=1)
            await session.commit()
            trigger_id = int(trigger.id)

            delivery = await _get_telegram_delivery(session, trigger_id)
            if delivery is None or delivery.status != "sent":
                status = "missing" if delivery is None else delivery.status
                print(f"telegram base delivery status={status}")
                return 3
            if delivery.telegram_message_id is None:
                print("telegram base delivery missing telegram_message_id")
                return 3

            print(
                "TELEGRAM_BASE_SMOKE_OK "
                f"telegram_message_id={delivery.telegram_message_id} "
                f"trigger_id={trigger_id}"
            )
            return 0
    except Exception as exc:
        LOGGER.exception("telegram base smoke failed: %s", safe_error_message(exc))
        return 1
    finally:
        if engine is not None:
            await engine.dispose()


def _build_parser() -> argparse.ArgumentParser:
    """Build the parser for the Telegram base smoke command."""
    return argparse.ArgumentParser(
        description="Send one synthetic AlertGate trigger through Telegram.",
    )


def _load_settings() -> TelegramBaseSmokeSettings:
    """Load smoke settings through the product Settings layer."""
    settings = Settings()
    return TelegramBaseSmokeSettings(
        database_url=settings.database_url.get_secret_value(),
        ai_explanations_enabled=settings.ai_explanations_enabled,
        telegram_bot_token=settings.telegram_bot_token.get_secret_value(),
        telegram_chat_id_alerts=settings.telegram_chat_id_alerts,
    )


def _validate_settings(settings: TelegramBaseSmokeSettings) -> str | None:
    """Return a safe validation error message or None."""
    if settings.ai_explanations_enabled:
        return "AI_EXPLANATIONS_ENABLED must be false for B0 smoke"
    if not settings.telegram_bot_token:
        return "missing TELEGRAM_BOT_TOKEN"
    if not settings.telegram_chat_id_alerts:
        return "missing TELEGRAM_CHAT_ID_ALERTS"
    if not settings.database_url:
        return "missing DATABASE_URL"
    return None


async def _get_telegram_delivery(
    session: AsyncSession,
    trigger_id: int,
) -> AlertDelivery | None:
    """Return the Telegram delivery row for one trigger id."""
    return cast(
        AlertDelivery | None,
        await session.scalar(
            select(AlertDelivery).where(
                AlertDelivery.alert_id == trigger_id,
                AlertDelivery.channel == "telegram",
            )
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
