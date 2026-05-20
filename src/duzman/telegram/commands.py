# src/duzman/telegram/commands.py
# Telegram command handlers. Pure command service methods are separated from
# python-telegram-bot transport adapters for unit testing.
"""Command handling for the single-user Telegram bot."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from duzman.db.repositories.alert_deliveries import AlertDeliveryRepository
from duzman.db.repositories.telegram_state import TelegramStateRepository
from duzman.telegram.config import TelegramSettings
from duzman.telegram.formatters import format_alerts_list
from duzman.telegram.state import is_authorized_chat, parse_snooze_until


class TelegramCommandService:
    """Execute Telegram commands against database state."""

    def __init__(
        self,
        *,
        settings: TelegramSettings,
        delivery_repository: AlertDeliveryRepository | None = None,
        state_repository: TelegramStateRepository | None = None,
    ) -> None:
        """Create the command service for one configured Telegram chat."""
        self._settings = settings
        self._deliveries = delivery_repository or AlertDeliveryRepository()
        self._state = state_repository or TelegramStateRepository()

    async def start(self, session: AsyncSession) -> str:
        """Return the `/start` command response."""
        status = await self.status(session)
        return "Duzman Telegram bot is alive.\n\n" + status

    async def help(self) -> str:
        """Return the `/help` command response."""
        return "\n".join(
            [
                "Commands:",
                "/start - check bot liveness",
                "/help - show commands",
                "/status - show delivery status",
                "/alerts - show last 5 AlertGate alerts",
                "/mute - mute Telegram delivery",
                "/unmute - enable Telegram delivery",
                "/snooze 1h|4h|24h - pause delivery temporarily",
            ]
        )

    async def status(self, session: AsyncSession) -> str:
        """Return the `/status` command response."""
        now = datetime.now(UTC)
        state = await self._state.get_or_create(session, now=now)
        last_alert = await self._deliveries.last_alert_ts(session)
        last_send = await self._deliveries.last_successful_send_ts(session)
        return "\n".join(
            [
                "Status: alive",
                "AlertGate: enabled",
                f"Telegram enabled: {state.enabled}",
                f"Muted: {state.muted}",
                f"Snooze until: {state.snooze_until.isoformat() if state.snooze_until else 'none'}",
                f"Poll interval: {self._settings.alert_poll_interval_seconds}s",
                f"Startup lookback: {self._settings.startup_lookback_hours}h",
                f"Last alert: {last_alert.isoformat() if last_alert else 'none'}",
                f"Last successful send: {last_send.isoformat() if last_send else 'none'}",
            ]
        )

    async def alerts(self, session: AsyncSession) -> str:
        """Return the `/alerts` command response."""
        alerts = await self._deliveries.list_recent_alerts(session, limit=5)
        return format_alerts_list(alerts)

    async def mute(self, session: AsyncSession) -> str:
        """Mute global Telegram delivery."""
        await self._state.set_muted(session, True, now=datetime.now(UTC))
        return "Telegram delivery muted."

    async def unmute(self, session: AsyncSession) -> str:
        """Unmute global Telegram delivery and clear snooze."""
        await self._state.set_muted(session, False, now=datetime.now(UTC))
        return "Telegram delivery unmuted."

    async def snooze(self, session: AsyncSession, argument: str) -> str:
        """Set global Telegram snooze."""
        try:
            snooze_until = parse_snooze_until(argument, now=datetime.now(UTC))
        except ValueError as exc:
            return str(exc)
        await self._state.set_snooze_until(session, snooze_until, now=datetime.now(UTC))
        return f"Telegram delivery snoozed until {snooze_until.isoformat()}."


def register_command_handlers(
    application: Application[Any, Any, Any, Any, Any, Any],
    *,
    session_factory: async_sessionmaker[AsyncSession],
    settings: TelegramSettings,
) -> None:
    """Register day-7 command handlers on a python-telegram-bot Application."""
    service = TelegramCommandService(settings=settings)

    async def handle_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, context, session_factory, settings, service.start)

    async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply_static(update, settings, await service.help())

    async def handle_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, context, session_factory, settings, service.status)

    async def handle_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply(update, context, session_factory, settings, service.alerts)

    async def handle_mute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply_mutating(update, context, session_factory, settings, service.mute)

    async def handle_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await _reply_mutating(update, context, session_factory, settings, service.unmute)

    async def handle_snooze(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        argument = context.args[0] if context.args else ""

        async def command(session: AsyncSession) -> str:
            return await service.snooze(session, argument)

        await _reply_mutating(update, context, session_factory, settings, command)

    application.add_handler(CommandHandler("start", handle_start))
    application.add_handler(CommandHandler("help", handle_help))
    application.add_handler(CommandHandler("status", handle_status))
    application.add_handler(CommandHandler("alerts", handle_alerts))
    application.add_handler(CommandHandler("mute", handle_mute))
    application.add_handler(CommandHandler("unmute", handle_unmute))
    application.add_handler(CommandHandler("snooze", handle_snooze))


async def _reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session_factory: async_sessionmaker[AsyncSession],
    settings: TelegramSettings,
    command: Any,
) -> None:
    """Run a read-only command and reply when the chat is authorized."""
    del context
    if not _authorized(update, settings):
        return
    async with session_factory() as session:
        text = await command(session)
    message = update.effective_message
    if message is not None:
        await message.reply_text(text)


async def _reply_mutating(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session_factory: async_sessionmaker[AsyncSession],
    settings: TelegramSettings,
    command: Any,
) -> None:
    """Run a mutating command, commit it, and reply when authorized."""
    del context
    if not _authorized(update, settings):
        return
    async with session_factory() as session:
        text = await command(session)
        await session.commit()
    message = update.effective_message
    if message is not None:
        await message.reply_text(text)


async def _reply_static(update: Update, settings: TelegramSettings, text: str) -> None:
    """Reply with static text when the chat is authorized."""
    if not _authorized(update, settings):
        return
    message = update.effective_message
    if message is not None:
        await message.reply_text(text)


def _authorized(update: Update, settings: TelegramSettings) -> bool:
    """Return whether the Telegram update belongs to the configured chat."""
    chat = update.effective_chat
    return chat is not None and is_authorized_chat(chat.id, settings.chat_id)
