# tests/dispatch/test_contract.py
# Dispatch contract tests. Verifies immutable pure data structures without
# database, network, or runtime wiring.
"""Tests for pure dispatch contract objects."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime

import pytest

from duzman.dispatch.contract import DispatchEvent, DispatchResult, build_dispatch_event

NOW = datetime(2026, 5, 31, 12, 0, tzinfo=UTC)
NAIVE_NOW = datetime(2026, 5, 31, 12, 0)


def test_dispatch_event_construction_success() -> None:
    """DispatchEvent should store valid primitive event fields."""
    event = DispatchEvent(
        pattern_trigger_id=1,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={"RSI_4h": 72.5},
    )

    assert event.pattern_trigger_id == 1
    assert event.asset == "BTC"
    assert event.pattern_name == "test_pattern"
    assert event.severity == "WARNING"
    assert event.ts == NOW
    assert event.conditions_snapshot == {"RSI_4h": 72.5}


def test_dispatch_event_is_immutable() -> None:
    """Assigning to a DispatchEvent attribute should fail."""
    event = DispatchEvent(
        pattern_trigger_id=1,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot={},
    )

    with pytest.raises(FrozenInstanceError):
        event.asset = "ETH"


def test_conditions_snapshot_is_shallow_immutable_by_design() -> None:
    """Document Spec 1 shallow immutability for conditions_snapshot.

    DispatchEvent is frozen, so callers cannot replace the attribute, but Spec
    1 does not deep-freeze the nested dict. Future code must treat
    conditions_snapshot as read-only by convention unless deep immutability is
    added later.
    """
    snapshot = {"RSI_4h": 72.5}
    event = DispatchEvent(
        pattern_trigger_id=1,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot=snapshot,
    )

    with pytest.raises(FrozenInstanceError):
        event.conditions_snapshot = {}

    snapshot["RSI_4h"] = 99.9

    assert event.conditions_snapshot is not None
    assert event.conditions_snapshot["RSI_4h"] == 99.9


def test_dispatch_event_rejects_naive_datetime() -> None:
    """DispatchEvent should reject naive timestamps."""
    with pytest.raises(ValueError, match="ts must be timezone-aware"):
        DispatchEvent(
            pattern_trigger_id=1,
            asset="BTC",
            pattern_name="test_pattern",
            severity="WARNING",
            ts=NAIVE_NOW,
            conditions_snapshot={},
        )


@pytest.mark.parametrize("pattern_trigger_id", [0, -1])
def test_dispatch_event_rejects_non_positive_id(pattern_trigger_id: int) -> None:
    """DispatchEvent should require a positive pattern_trigger_id."""
    with pytest.raises(ValueError, match="pattern_trigger_id must be positive"):
        DispatchEvent(
            pattern_trigger_id=pattern_trigger_id,
            asset="BTC",
            pattern_name="test_pattern",
            severity="WARNING",
            ts=NOW,
            conditions_snapshot={},
        )


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("asset", ""),
        ("pattern_name", " "),
        ("severity", ""),
    ],
)
def test_dispatch_event_rejects_empty_required_strings(
    field_name: str,
    field_value: str,
) -> None:
    """DispatchEvent should require non-empty string fields."""
    kwargs = {
        "pattern_trigger_id": 1,
        "asset": "BTC",
        "pattern_name": "test_pattern",
        "severity": "WARNING",
        "ts": NOW,
        "conditions_snapshot": {},
        field_name: field_value,
    }

    with pytest.raises(ValueError, match=f"{field_name} must be a non-empty string"):
        DispatchEvent(**kwargs)


def test_dispatch_event_accepts_none_conditions_snapshot() -> None:
    """DispatchEvent should allow absent condition snapshots."""
    event = DispatchEvent(
        pattern_trigger_id=1,
        asset="BTC",
        pattern_name="test_pattern",
        severity="WARNING",
        ts=NOW,
        conditions_snapshot=None,
    )

    assert event.conditions_snapshot is None


def test_build_dispatch_event_success() -> None:
    """build_dispatch_event should return a validated DispatchEvent."""
    event = build_dispatch_event(
        pattern_trigger_id=42,
        asset="ETH",
        pattern_name="distribution_top_candidate_majors",
        severity="CRITICAL",
        ts=NOW,
        conditions_snapshot={"OI_CHANGE_24H": 18.0},
    )

    assert event == DispatchEvent(
        pattern_trigger_id=42,
        asset="ETH",
        pattern_name="distribution_top_candidate_majors",
        severity="CRITICAL",
        ts=NOW,
        conditions_snapshot={"OI_CHANGE_24H": 18.0},
    )


@pytest.mark.parametrize("pattern_trigger_id", [0, -1])
def test_build_dispatch_event_rejects_non_positive_id(pattern_trigger_id: int) -> None:
    """build_dispatch_event should require a positive pattern_trigger_id."""
    with pytest.raises(ValueError, match="pattern_trigger_id must be positive"):
        build_dispatch_event(
            pattern_trigger_id=pattern_trigger_id,
            asset="BTC",
            pattern_name="test_pattern",
            severity="WARNING",
            ts=NOW,
            conditions_snapshot={},
        )


def test_build_dispatch_event_rejects_empty_asset() -> None:
    """build_dispatch_event should reject an empty asset value."""
    with pytest.raises(ValueError, match="asset must be a non-empty string"):
        build_dispatch_event(
            pattern_trigger_id=1,
            asset="",
            pattern_name="test_pattern",
            severity="WARNING",
            ts=NOW,
            conditions_snapshot={},
        )


def test_build_dispatch_event_rejects_empty_pattern_name() -> None:
    """build_dispatch_event should reject an empty pattern_name value."""
    with pytest.raises(ValueError, match="pattern_name must be a non-empty string"):
        build_dispatch_event(
            pattern_trigger_id=1,
            asset="BTC",
            pattern_name="",
            severity="WARNING",
            ts=NOW,
            conditions_snapshot={},
        )


def test_build_dispatch_event_rejects_empty_severity() -> None:
    """build_dispatch_event should reject an empty severity value."""
    with pytest.raises(ValueError, match="severity must be a non-empty string"):
        build_dispatch_event(
            pattern_trigger_id=1,
            asset="BTC",
            pattern_name="test_pattern",
            severity="",
            ts=NOW,
            conditions_snapshot={},
        )


def test_build_dispatch_event_rejects_naive_datetime() -> None:
    """build_dispatch_event should reject naive timestamps."""
    with pytest.raises(ValueError, match="ts must be timezone-aware"):
        build_dispatch_event(
            pattern_trigger_id=1,
            asset="BTC",
            pattern_name="test_pattern",
            severity="WARNING",
            ts=NAIVE_NOW,
            conditions_snapshot={},
        )


def test_dispatch_result_errors_are_immutable_tuple() -> None:
    """DispatchResult errors should be stored as an immutable tuple."""
    result = DispatchResult(
        telegram_status="sent",
        explanation_status="skipped_disabled",
        errors=("transient telegram timeout",),
    )

    assert result.errors == ("transient telegram timeout",)
    assert isinstance(result.errors, tuple)
