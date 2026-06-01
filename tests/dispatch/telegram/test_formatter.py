# tests/dispatch/telegram/test_formatter.py
# Telegram formatter tests. Verifies deterministic MarkdownV2 rendering without
# network, secrets, or runtime dependencies.
"""Tests for Telegram dispatch message formatting."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from duzman.dispatch.contract import DispatchEvent
from duzman.dispatch.telegram.formatter import format_dispatch_event_for_telegram

FIXTURES_DIR = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
FAKE_TOKEN = "test-bot-token-do-not-use"
FAKE_CHAT_ID = "test-chat-id-12345"


def test_formatter_matches_basic_golden_message() -> None:
    """A basic event without conditions should match the golden file."""
    event = DispatchEvent(
        pattern_trigger_id=1,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={},
    )

    assert format_dispatch_event_for_telegram(event) == _read_fixture(
        "golden_message_basic.txt"
    )


def test_formatter_matches_snapshot_golden_message() -> None:
    """An event with conditions should match the golden file."""
    event = DispatchEvent(
        pattern_trigger_id=2,
        asset="ETH",
        pattern_name="distribution_top_candidate_majors",
        severity="CRITICAL",
        ts=NOW,
        conditions_snapshot={
            "RSI_4h": 72.5,
            "OI_CHANGE_24H": 18.0,
            "active": True,
        },
    )

    assert format_dispatch_event_for_telegram(event) == _read_fixture(
        "golden_message_with_snapshot.txt"
    )


def test_formatter_renders_none_conditions_snapshot() -> None:
    """A None condition snapshot should render as no conditions."""
    event = DispatchEvent(
        pattern_trigger_id=3,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot=None,
    )

    message = format_dispatch_event_for_telegram(event)

    assert "Conditions:\nnone" in message


def test_formatter_escapes_markdown_v2_user_fields() -> None:
    """MarkdownV2 special characters in event fields should be escaped."""
    event = DispatchEvent(
        pattern_trigger_id=4,
        asset="BTC/USD",
        pattern_name="mean_reversion*(test)",
        severity="CRITICAL!",
        ts=NOW,
        conditions_snapshot={"price.delta": "+1.2%"},
    )

    message = format_dispatch_event_for_telegram(event)

    assert "*CRITICAL\\!*" in message
    assert "mean\\_reversion\\*\\(test\\)" in message
    assert "price\\.delta: \\+1\\.2%" in message


def test_formatter_truncates_large_conditions_snapshot() -> None:
    """Condition snapshots above the Spec 2 cap should be truncated."""
    event = DispatchEvent(
        pattern_trigger_id=5,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={f"metric_{index}": index for index in range(25)},
    )

    message = format_dispatch_event_for_telegram(event)

    assert "\\- metric\\_19: 19" in message
    assert "metric\\_20" not in message
    assert "\\- \\(\\.\\.\\.\\)" in message


def test_formatter_does_not_include_token_or_chat_id_substrings() -> None:
    """Formatter output should include only DispatchEvent fields."""
    event = DispatchEvent(
        pattern_trigger_id=6,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={},
    )

    message = format_dispatch_event_for_telegram(event)

    assert FAKE_TOKEN not in message
    assert FAKE_CHAT_ID not in message


def _read_fixture(filename: str) -> str:
    """Read a golden message fixture."""
    return (FIXTURES_DIR / filename).read_text(encoding="utf-8").rstrip("\n")
