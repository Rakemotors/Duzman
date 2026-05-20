# src/duzman/telegram/sender.py
# Telegram sender. Sends AlertGate alerts through an injected client and records
# delivery rows without coupling AlertGate to Telegram.
"""Telegram alert sender with delivery persistence."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Bot

from duzman.ai.explanation_service import create_pending_explanation
from duzman.db.models import AlertDelivery, PatternTrigger
from duzman.db.repositories.alert_deliveries import AlertDeliveryRepository
from duzman.db.repositories.telegram_state import TelegramStateRepository
from duzman.settings import settings
from duzman.telegram.formatters import format_alert

LOGGER = logging.getLogger(__name__)
EXPLANATION_PREFIX = "🤖 Объяснение:\n\n"


class TelegramClient(Protocol):
    """Minimal async Telegram client used by the sender."""

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> int:
        """Send one text message to a Telegram chat and return message id."""


class TelegramBotClient:
    """python-telegram-bot adapter for TelegramClient."""

    def __init__(self, token: str) -> None:
        """Create a Bot API client without performing network calls."""
        self._bot = Bot(token=token)

    async def send_message(
        self,
        *,
        chat_id: str,
        text: str,
        reply_to_message_id: int | None = None,
    ) -> int:
        """Send one text message via Telegram Bot API and return message id."""
        message = await self._bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
        )
        return int(message.message_id)


class TelegramAlertSender:
    """Send AlertGate alerts and persist per-alert Telegram delivery state."""

    def __init__(
        self,
        client: TelegramClient,
        chat_id: str,
        *,
        delivery_repository: AlertDeliveryRepository | None = None,
        state_repository: TelegramStateRepository | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        ai_explanations_enabled: bool | None = None,
        anthropic_api_key_configured: bool | None = None,
        explanation_max_input_chars: int | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_delays: Sequence[float] = (1.0, 2.0, 4.0),
    ) -> None:
        """Create a sender for one configured Telegram chat."""
        self._client = client
        self._chat_id = chat_id
        self._deliveries = delivery_repository or AlertDeliveryRepository()
        self._state = state_repository or TelegramStateRepository()
        self._session_factory = session_factory
        self._ai_explanations_enabled = (
            settings.ai_explanations_enabled
            if ai_explanations_enabled is None
            else ai_explanations_enabled
        )
        self._anthropic_api_key_configured = (
            bool(settings.anthropic_api_key)
            if anthropic_api_key_configured is None
            else anthropic_api_key_configured
        )
        self._explanation_max_input_chars = (
            settings.ai_explanation_max_input_chars
            if explanation_max_input_chars is None
            else explanation_max_input_chars
        )
        self._sleep = sleep
        self._retry_delays = retry_delays

    async def send_alert(self, session: AsyncSession, alert: PatternTrigger) -> str:
        """Send one alert unless Telegram delivery is muted or snoozed.

        Returns:
            Final delivery status: `sent`, `failed`, or `snoozed`.
        """
        now = datetime.now(UTC)
        can_send, snooze_until = await self._state.is_delivery_enabled(session, now=now)
        if not can_send:
            await self._deliveries.create_or_update(
                session,
                int(alert.id),
                "snoozed",
                snooze_until=snooze_until,
                now=now,
            )
            return "snoozed"

        text = format_alert(alert)
        error_message = ""
        for attempt, delay in enumerate(self._retry_delays, start=1):
            try:
                message_id = await self._client.send_message(chat_id=self._chat_id, text=text)
                sent_at = datetime.now(UTC)
                delivery = await self._deliveries.create_or_update(
                    session,
                    int(alert.id),
                    "sent",
                    sent_at=sent_at,
                    telegram_message_id=message_id,
                    now=sent_at,
                )
                await self._create_pending_explanation_if_enabled(session, alert, delivery)
                return "sent"
            except Exception as exc:  # pragma: no cover - exact client errors vary.
                error_message = _safe_error_message(exc)
                if attempt < len(self._retry_delays):
                    await self._sleep(delay)

        failed_at = datetime.now(UTC)
        await self._deliveries.create_or_update(
            session,
            int(alert.id),
            "failed",
            error_message=error_message,
            now=failed_at,
        )
        return "failed"

    async def send_text(self, text: str) -> None:
        """Send one already formatted Telegram text message."""
        await self._client.send_message(chat_id=self._chat_id, text=text)

    async def send_explanation(self, alert_delivery_id: int, text: str) -> None:
        """Send an AI explanation as a reply to the base Telegram alert."""
        if self._session_factory is None:
            LOGGER.warning("telegram_explanation_sender_missing_session_factory")
            return

        async with self._session_factory() as session:
            delivery = await session.get(AlertDelivery, alert_delivery_id)
            if delivery is None:
                LOGGER.warning(
                    "telegram_explanation_delivery_missing",
                    extra={"alert_delivery_id": alert_delivery_id},
                )
                return
            if delivery.telegram_message_id is None:
                LOGGER.warning(
                    "telegram_explanation_base_message_missing",
                    extra={"alert_delivery_id": alert_delivery_id},
                )
                return
            await self._client.send_message(
                chat_id=self._chat_id,
                text=EXPLANATION_PREFIX + text,
                reply_to_message_id=int(delivery.telegram_message_id),
            )

    async def _create_pending_explanation_if_enabled(
        self,
        session: AsyncSession,
        alert: PatternTrigger,
        delivery: AlertDelivery,
    ) -> None:
        """Create a day-8 explanation task after successful base alert delivery."""
        if not self._ai_explanations_enabled or not self._anthropic_api_key_configured:
            return
        await create_pending_explanation(
            session,
            alert,
            alert_delivery_id=int(delivery.id),
            max_input_chars=self._explanation_max_input_chars,
        )


def _safe_error_message(exc: Exception) -> str:
    """Return a bounded error string safe for persistence and logs."""
    text = str(exc).replace("\n", " ").replace("\r", " ").strip()
    return text[:500]
