# src/duzman/telegram/state.py
# Telegram command state helpers. Keeps mute and snooze parsing separate from
# command transport code.
"""State helpers for Telegram mute and snooze commands."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

SNOOZE_DURATIONS = {
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
}


def parse_snooze_until(argument: str, *, now: datetime | None = None) -> datetime:
    """Parse a supported snooze duration and return the UTC deadline.

    Raises:
        ValueError: If the duration is not one of the day-7 supported values.
    """
    current = now or datetime.now(UTC)
    duration = SNOOZE_DURATIONS.get(argument.strip().lower())
    if duration is None:
        raise ValueError("supported snooze values: 1h, 4h, 24h")
    return current + duration


def is_authorized_chat(chat_id: object, allowed_chat_id: str | None) -> bool:
    """Return whether an incoming Telegram chat id matches configuration."""
    return allowed_chat_id is not None and str(chat_id) == str(allowed_chat_id)
