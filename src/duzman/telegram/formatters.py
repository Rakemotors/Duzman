# src/duzman/telegram/formatters.py
# AlertGate text formatting. Converts PatternTrigger rows into bounded plain
# text messages safe for Telegram without enabling rich parsing.
"""Format AlertGate alerts and digests for Telegram."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from duzman.db.models import PatternTrigger

MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def format_alert(alert: PatternTrigger) -> str:
    """Return a bounded single-alert Telegram message."""
    lines = [
        "Duzman Alert",
        f"ID: {alert.id}",
        f"Time: {_format_ts(alert.ts)}",
        f"Asset: {alert.asset}",
        f"Rule: {alert.pattern_name}",
        f"Severity: {alert.severity}",
        f"Message: {_preview(alert)}",
    ]
    return _truncate("\n".join(lines))


def format_alerts_list(alerts: list[PatternTrigger]) -> str:
    """Return a compact list of recent AlertGate alerts."""
    if not alerts:
        return "No recent alerts."
    lines = ["Recent alerts:"]
    for alert in alerts:
        lines.append(
            f"#{alert.id} { _format_ts(alert.ts) } {alert.asset} "
            f"{alert.pattern_name}: {_preview(alert, limit=80)}"
        )
    return _truncate("\n".join(lines))


def format_startup_digest(alerts: list[PatternTrigger]) -> list[str]:
    """Return one or more bounded startup digest messages."""
    if not alerts:
        return ["Startup digest: no unsent alerts in the lookback window."]
    messages: list[str] = []
    current = "Startup digest: unsent alerts in the lookback window"
    for alert in alerts:
        line = (
            f"\n#{alert.id} { _format_ts(alert.ts) } {alert.asset} "
            f"{alert.pattern_name}: {_preview(alert, limit=120)}"
        )
        if len(current) + len(line) > MAX_TELEGRAM_MESSAGE_LENGTH:
            messages.append(current)
            current = "Startup digest continued" + line
        else:
            current += line
    messages.append(current)
    return messages


def _preview(alert: PatternTrigger, *, limit: int = 500) -> str:
    """Return a short human-readable alert explanation."""
    if alert.ai_explanation:
        return _single_line(alert.ai_explanation, limit=limit)
    snapshot = alert.conditions_snapshot or {}
    if not snapshot:
        return "No condition snapshot."
    rendered = ", ".join(
        f"{key}={value}" for key, value in sorted(snapshot.items()) if key != "gate_decision"
    )
    return _single_line(rendered or "ALLOW", limit=limit)


def _single_line(value: Any, *, limit: int) -> str:
    """Normalize a value into one bounded line."""
    text = str(value).replace("\n", " ").replace("\r", " ").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def _format_ts(value: datetime) -> str:
    """Format a timestamp for Telegram command output."""
    return value.isoformat()


def _truncate(text: str) -> str:
    """Bound text to Telegram's message length limit."""
    if len(text) <= MAX_TELEGRAM_MESSAGE_LENGTH:
        return text
    return text[: MAX_TELEGRAM_MESSAGE_LENGTH - 3].rstrip() + "..."
