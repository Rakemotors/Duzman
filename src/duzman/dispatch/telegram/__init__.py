# src/duzman/dispatch/telegram/__init__.py
# Telegram dispatch package. Exports the inert Phase 2 base sender, client,
# formatter, and result contract for future runtime wiring.
"""Telegram base sender package."""

from duzman.dispatch.telegram.client import TelegramHttpClient
from duzman.dispatch.telegram.formatter import format_dispatch_event_for_telegram
from duzman.dispatch.telegram.result import TelegramSendResult
from duzman.dispatch.telegram.sender import TelegramBaseSender

__all__ = [
    "TelegramBaseSender",
    "TelegramHttpClient",
    "TelegramSendResult",
    "format_dispatch_event_for_telegram",
]
