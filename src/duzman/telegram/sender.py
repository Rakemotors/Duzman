# src/duzman/telegram/sender.py
# Telegram sender. Sends AlertGate alerts through an injected client and records
# delivery rows without coupling AlertGate to Telegram.
"""Telegram alert sender with delivery persistence."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from duzman.db.models import PatternTrigger
from duzman.db.repositories.alert_deliveries import AlertDeliveryRepository
from duzman.db.repositories.telegram_state import TelegramStateRepository
from duzman.telegram.formatters import format_alert


class TelegramClient(Protocol):
    """Minimal async Telegram client used by the sender."""

    async def send_message(self, *, chat_id: str, text: str) -> None:
        """Send one text message to a Telegram chat."""


class TelegramBotClient:
    """python-telegram-bot adapter for TelegramClient."""

    def __init__(self, token: str) -> None:
        """Create a Bot API client without performing network calls."""
        self._bot = Bot(token=token)

    async def send_message(self, *, chat_id: str, text: str) -> None:
        """Send one text message via Telegram Bot API."""
        await self._bot.send_message(chat_id=chat_id, text=text)


class TelegramAlertSender:
    """Send AlertGate alerts and persist per-alert Telegram delivery state."""

    def __init__(
        self,
        client: TelegramClient,
        chat_id: str,
        *,
        delivery_repository: AlertDeliveryRepository | None = None,
        state_repository: TelegramStateRepository | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        retry_delays: Sequence[float] = (1.0, 2.0, 4.0),
    ) -> None:
        """Create a sender for one configured Telegram chat."""
        self._client = client
        self._chat_id = chat_id
        self._deliveries = delivery_repository or AlertDeliveryRepository()
        self._state = state_repository or TelegramStateRepository()
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
                await self._client.send_message(chat_id=self._chat_id, text=text)
                sent_at = datetime.now(UTC)
                await self._deliveries.create_or_update(
                    session,
                    int(alert.id),
                    "sent",
                    sent_at=sent_at,
                    now=sent_at,
                )
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


def _safe_error_message(exc: Exception) -> str:
    """Return a bounded error string safe for persistence and logs."""
    text = str(exc).replace("\n", " ").replace("\r", " ").strip()
    return text[:500]
