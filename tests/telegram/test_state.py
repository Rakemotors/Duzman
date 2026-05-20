from datetime import UTC, datetime, timedelta

import pytest

from duzman.telegram.state import is_authorized_chat, parse_snooze_until


def test_parse_snooze_until_accepts_supported_values() -> None:
    """Snooze parsing should support only day-7 durations."""
    now = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)

    assert parse_snooze_until("4h", now=now) == now + timedelta(hours=4)


def test_parse_snooze_until_rejects_unknown_value() -> None:
    """Unknown snooze values should return a clear command error."""
    with pytest.raises(ValueError, match="supported snooze values"):
        parse_snooze_until("2h")


def test_is_authorized_chat_compares_stringified_chat_ids() -> None:
    """Telegram integer chat ids should match string env configuration."""
    assert is_authorized_chat(12345, "12345")
    assert not is_authorized_chat(12345, "999")
