# src/duzman/telegram/poller.py
# Telegram DB poller. Reads AlertGate PatternTrigger rows and delegates sending
# through TelegramAlertSender.
"""Database polling loop for Telegram AlertGate delivery."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from duzman.db.repositories.alert_deliveries import AlertDeliveryRepository
from duzman.db.repositories.telegram_state import TelegramStateRepository
from duzman.telegram.formatters import format_startup_digest
from duzman.telegram.sender import TelegramAlertSender


class TelegramAlertPoller:
    """Poll the database for unsent AlertGate alerts."""

    def __init__(
        self,
        sender: TelegramAlertSender,
        *,
        delivery_repository: AlertDeliveryRepository | None = None,
        state_repository: TelegramStateRepository | None = None,
        rate_limit_seconds: float = 1.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """Create a poller with explicit sender and rate limiting."""
        self._sender = sender
        self._deliveries = delivery_repository or AlertDeliveryRepository()
        self._state = state_repository or TelegramStateRepository()
        self._rate_limit_seconds = rate_limit_seconds
        self._sleep = sleep

    async def run_once(self, session: AsyncSession, *, limit: int = 20) -> int:
        """Send one batch of currently pending alerts.

        Returns:
            Number of alerts inspected for delivery.
        """
        alerts = await self._deliveries.list_pending_alerts(session, limit=limit)
        for index, alert in enumerate(alerts):
            await self._sender.send_alert(session, alert)
            if index < len(alerts) - 1:
                await self._sleep(self._rate_limit_seconds)
        return len(alerts)

    async def send_startup_digest(
        self,
        session: AsyncSession,
        *,
        lookback_hours: int,
        limit: int = 50,
    ) -> int:
        """Send a bounded digest of recent unsent alerts and mark them delivered."""
        since = datetime.now(UTC) - timedelta(hours=lookback_hours)
        alerts = await self._deliveries.list_unsent_since(session, since=since, limit=limit)
        if not alerts:
            return 0

        now = datetime.now(UTC)
        can_send, snooze_until = await self._state.is_delivery_enabled(session, now=now)
        if not can_send:
            for alert in alerts:
                await self._deliveries.create_or_update(
                    session,
                    int(alert.id),
                    "snoozed",
                    snooze_until=snooze_until,
                    now=now,
                )
            return len(alerts)

        for message in format_startup_digest(alerts):
            await self._sender.send_text(message)

        sent_at = datetime.now(UTC)
        for alert in alerts:
            await self._deliveries.create_or_update(
                session,
                int(alert.id),
                "sent",
                sent_at=sent_at,
                now=sent_at,
            )
        return len(alerts)


async def run_polling_loop(
    session_factory: async_sessionmaker[AsyncSession],
    poller: TelegramAlertPoller,
    *,
    poll_interval_seconds: int,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run Telegram DB polling until cancelled or stop_event is set."""
    while stop_event is None or not stop_event.is_set():
        async with session_factory() as session:
            await poller.run_once(session)
            await session.commit()
        await asyncio.sleep(poll_interval_seconds)
