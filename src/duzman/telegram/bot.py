# src/duzman/telegram/bot.py
# Managed Telegram worker. Builds long-polling and DB-polling tasks explicitly,
# with no network activity at import time.
"""Managed Telegram long-polling worker."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram.ext import Application

from duzman.telegram.commands import register_command_handlers
from duzman.telegram.config import TelegramSettings, load_telegram_settings
from duzman.telegram.poller import TelegramAlertPoller, run_polling_loop
from duzman.telegram.sender import TelegramAlertSender, TelegramBotClient

LOGGER = logging.getLogger(__name__)


class TelegramWorker:
    """Run Telegram long polling and AlertGate delivery polling as managed tasks."""

    def __init__(
        self,
        *,
        settings: TelegramSettings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Create a worker; call run() to start network activity."""
        self._settings = settings
        self._session_factory = session_factory

    async def run(self, *, stop_event: asyncio.Event | None = None) -> None:
        """Run startup digest, DB polling, and Telegram getUpdates polling."""
        disabled_reason = self._settings.safe_disabled_reason
        if disabled_reason is not None:
            LOGGER.info("telegram_worker_disabled", extra={"reason": disabled_reason})
            return

        assert self._settings.bot_token is not None
        token = self._settings.bot_token.get_secret_value()
        assert self._settings.chat_id is not None
        client = TelegramBotClient(token)
        sender = TelegramAlertSender(client, self._settings.chat_id)
        poller = TelegramAlertPoller(sender)
        application = self._build_application(token)

        async with self._session_factory() as session:
            await poller.send_startup_digest(
                session,
                lookback_hours=self._settings.startup_lookback_hours,
            )
            await session.commit()

        polling_task = asyncio.create_task(
            run_polling_loop(
                self._session_factory,
                poller,
                poll_interval_seconds=self._settings.alert_poll_interval_seconds,
                stop_event=stop_event,
            )
        )
        try:
            await application.initialize()
            await application.start()
            assert application.updater is not None
            await application.updater.start_polling()
            if stop_event is None:
                await asyncio.Event().wait()
            else:
                await stop_event.wait()
        finally:
            polling_task.cancel()
            await _cancel_task(polling_task)
            if application.updater is not None:
                await application.updater.stop()
            await application.stop()
            await application.shutdown()

    def _build_application(self, token: str) -> Application[Any, Any, Any, Any, Any, Any]:
        """Build the python-telegram-bot application and command handlers."""
        application = Application.builder().token(token).build()
        register_command_handlers(
            application,
            session_factory=self._session_factory,
            settings=self._settings,
        )
        return application


def build_telegram_worker(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    settings: TelegramSettings | None = None,
) -> TelegramWorker:
    """Build a TelegramWorker without starting it."""
    return TelegramWorker(
        settings=settings or load_telegram_settings(),
        session_factory=session_factory,
    )


def start_telegram_background_task(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    settings: TelegramSettings | None = None,
    stop_event: asyncio.Event | None = None,
) -> asyncio.Task[None]:
    """Start TelegramWorker as an explicit managed asyncio task."""
    worker = build_telegram_worker(session_factory, settings=settings)
    return asyncio.create_task(worker.run(stop_event=stop_event))


async def _cancel_task(task: asyncio.Task[None]) -> None:
    """Cancel a task and suppress the expected cancellation exception."""
    try:
        await task
    except asyncio.CancelledError:
        pass
