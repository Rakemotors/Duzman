# src/duzman/telegram/__init__.py
# Telegram integration package. Exports explicit worker builders only; importing
# this package never starts polling or performs network calls.
"""Telegram integration for AlertGate delivery."""

from duzman.telegram.bot import TelegramWorker, build_telegram_worker

__all__ = ["TelegramWorker", "build_telegram_worker"]
