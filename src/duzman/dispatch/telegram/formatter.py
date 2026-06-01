# src/duzman/dispatch/telegram/formatter.py
# Telegram message formatter. Renders DispatchEvent values into deterministic
# MarkdownV2 text without I/O or runtime dependencies.
"""Telegram MarkdownV2 formatter for dispatch events."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC

from duzman.dispatch.contract import DispatchEvent

MAX_CONDITIONS = 20
MARKDOWN_V2_SPECIAL_CHARS = frozenset("\\_*[]()~`>#+-=|{}.!")


def format_dispatch_event_for_telegram(event: DispatchEvent) -> str:
    """Render a dispatch event as deterministic Telegram MarkdownV2 text."""
    timestamp = event.ts.astimezone(UTC).isoformat()
    lines = [
        f"*{_escape_markdown_v2(event.severity)}* \\- "
        f"{_escape_markdown_v2(event.pattern_name)}",
        f"Asset: *{_escape_markdown_v2(event.asset)}*",
        f"Time: {_escape_markdown_v2(timestamp)}",
        "",
        "Conditions:",
    ]

    condition_items = event.conditions_snapshot.items() if event.conditions_snapshot else []
    lines.extend(_format_conditions(condition_items))
    return "\n".join(lines)


def _format_conditions(conditions: Iterable[tuple[str, object]]) -> list[str]:
    """Format up to MAX_CONDITIONS condition rows in stable input order."""
    rows = list(conditions)
    if not rows:
        return ["none"]

    visible_rows = rows[:MAX_CONDITIONS]
    lines = [
        f"\\- {_escape_markdown_v2(str(key))}: {_escape_markdown_v2(_stringify_value(value))}"
        for key, value in visible_rows
    ]
    if len(rows) > MAX_CONDITIONS:
        lines.append("\\- \\(\\.\\.\\.\\)")
    return lines


def _stringify_value(value: object) -> str:
    """Convert a condition value to deterministic text."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _escape_markdown_v2(value: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    return "".join(f"\\{char}" if char in MARKDOWN_V2_SPECIAL_CHARS else char for char in value)
