from datetime import UTC, datetime

from duzman.db.models import PatternTrigger
from duzman.telegram.formatters import format_alert, format_alerts_list, format_startup_digest


def test_format_alert_contains_core_fields() -> None:
    """Alert formatting should expose the core AlertGate fields."""
    alert = _alert()

    text = format_alert(alert)

    assert "Duzman Alert" in text
    assert "ID: 7" in text
    assert "Asset: BTC" in text
    assert "Rule: rsi_overheated" in text
    assert "RSI_4h=82" in text


def test_format_alerts_list_handles_empty_list() -> None:
    """The `/alerts` formatter should be explicit when no alerts exist."""
    assert format_alerts_list([]) == "No recent alerts."


def test_startup_digest_is_bounded_and_marked() -> None:
    """Startup digest should carry an explicit marker for operator clarity."""
    messages = format_startup_digest([_alert()])

    assert len(messages) == 1
    assert messages[0].startswith("Startup digest")


def _alert() -> PatternTrigger:
    """Build a minimal PatternTrigger for formatter tests."""
    return PatternTrigger(
        id=7,
        ts=datetime(2026, 5, 20, 12, 0, tzinfo=UTC),
        pattern_name="rsi_overheated",
        asset="BTC",
        severity="WARNING",
        conditions_snapshot={"gate_decision": "ALLOW", "RSI_4h": 82},
        alert_sent=False,
    )
