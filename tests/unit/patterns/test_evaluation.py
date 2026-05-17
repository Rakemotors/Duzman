"""Tests for deterministic Pattern Engine evaluation."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from duzman.patterns.evaluation import PatternMatch, evaluate_patterns
from duzman.patterns.models import Condition, ConditionGroup, PatternDefinition
from duzman.patterns.snapshot import AssetMetrics, MetricsSnapshot

BUILT_AT = datetime(2026, 5, 17, 12, 0, tzinfo=timezone.utc)


def test_no_patterns_returns_empty_list() -> None:
    """No patterns should produce no matches."""
    assert evaluate_patterns([], _snapshot()) == []


def test_pattern_not_in_applies_to_skipped() -> None:
    """Assets outside applies_to should be skipped."""
    pattern = _pattern(applies_to=["BTC"])

    assert evaluate_patterns([pattern], _snapshot(asset_values={"SOL": {"RSI_4h": 70}})) == []


def test_simple_all_match() -> None:
    """A pattern should match when every all condition is true."""
    pattern = _pattern(
        conditions=[
            _condition("RSI_4h", ">", 60),
            _condition("funding_rate_avg", ">", 0.01),
        ]
    )

    matches = evaluate_patterns([pattern], _snapshot())

    assert len(matches) == 1
    assert matches[0].pattern_name == "test_pattern"
    assert matches[0].asset == "BTC"


def test_simple_all_one_fails() -> None:
    """A pattern should not match when one all condition is false."""
    pattern = _pattern(
        conditions=[
            _condition("RSI_4h", ">", 60),
            _condition("funding_rate_avg", ">", 0.1),
        ]
    )

    assert evaluate_patterns([pattern], _snapshot()) == []


def test_operator_gt() -> None:
    """The greater-than operator should be supported."""
    assert _matches(_condition("RSI_4h", ">", 60))


def test_operator_lt() -> None:
    """The less-than operator should be supported."""
    assert _matches(_condition("RSI_4h", "<", 80))


def test_operator_gte() -> None:
    """The greater-than-or-equal operator should be supported."""
    assert _matches(_condition("RSI_4h", ">=", 65))


def test_operator_lte() -> None:
    """The less-than-or-equal operator should be supported."""
    assert _matches(_condition("RSI_4h", "<=", 65))


def test_operator_eq() -> None:
    """The equality operator should be supported."""
    assert _matches(_condition("RSI_4h", "==", 65))


def test_operator_neq() -> None:
    """The inequality operator should be supported."""
    assert _matches(_condition("RSI_4h", "!=", 66))


def test_none_metric_blocks_match() -> None:
    """A None metric should block the whole pattern match."""
    pattern = _pattern(conditions=[_condition("RSI_4h", ">", 60)])
    snapshot = _snapshot(asset_values={"BTC": {"RSI_4h": None}})

    assert evaluate_patterns([pattern], snapshot) == []


def test_per_asset_threshold_used() -> None:
    """Per-asset thresholds should override scalar condition values."""
    pattern = _pattern(
        conditions=[
            Condition(
                metric="etf_cum_flow_5d_usd",
                operator=">",
                per_asset_thresholds={"BTC": 1_000_000_000.0},
            )
        ]
    )
    snapshot = _snapshot(asset_values={"BTC": {"etf_cum_flow_5d_usd": 2_000_000_000.0}})

    assert len(evaluate_patterns([pattern], snapshot)) == 1


def test_per_asset_threshold_missing_key_logs_misconfigured(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A missing per-asset threshold key should log and block the match."""
    pattern = _pattern(
        applies_to=["SOL"],
        conditions=[
            Condition(
                metric="etf_cum_flow_5d_usd",
                operator=">",
                per_asset_thresholds={"BTC": 1_000_000_000.0},
            )
        ],
    )
    snapshot = _snapshot(asset_values={"SOL": {"etf_cum_flow_5d_usd": 2_000_000_000.0}})

    with caplog.at_level(logging.WARNING):
        matches = evaluate_patterns([pattern], snapshot)

    assert matches == []
    assert "pattern_misconfigured" in caplog.text
    assert "metric_name=etf_cum_flow_5d_usd" in caplog.text


def test_global_metric_read_from_global() -> None:
    """Global metrics should be read from snapshot.global_metrics."""
    pattern = _pattern(conditions=[_condition("fear_greed_index", ">", 70)])
    snapshot = _snapshot(global_metrics={"fear_greed_index": 80.0})

    assert len(evaluate_patterns([pattern], snapshot)) == 1


def test_conditions_snapshot_contains_only_used_metrics() -> None:
    """Match snapshots should include only metrics referenced by conditions."""
    pattern = _pattern(
        conditions=[
            _condition("RSI_4h", ">", 60),
            _condition("funding_rate_avg", ">", 0.01),
        ]
    )
    snapshot = _snapshot(
        asset_values={"BTC": {"RSI_4h": 65.0, "funding_rate_avg": 0.02, "RSI_1h": 10.0}}
    )

    match = evaluate_patterns([pattern], snapshot)[0]

    assert match.conditions_snapshot == {"RSI_4h": 65.0, "funding_rate_avg": 0.02}


def test_evaluated_at_equals_snapshot_built_at() -> None:
    """A match should carry the snapshot built_at timestamp."""
    match = evaluate_patterns([_pattern()], _snapshot())[0]

    assert match.evaluated_at == BUILT_AT


def test_severity_propagated_from_pattern() -> None:
    """A match should carry pattern severity."""
    match = evaluate_patterns([_pattern(severity="WARNING")], _snapshot())[0]

    assert match.severity == "WARNING"


def test_two_patterns_two_assets_stable_order() -> None:
    """Matches should be sorted by pattern name and asset."""
    first = _pattern(name="b_pattern", applies_to=["SOL", "BTC"])
    second = _pattern(name="a_pattern", applies_to=["SOL", "BTC"])
    snapshot = _snapshot(
        asset_values={
            "SOL": {"RSI_4h": 70.0, "funding_rate_avg": 0.02},
            "BTC": {"RSI_4h": 70.0, "funding_rate_avg": 0.02},
        }
    )

    matches = evaluate_patterns([first, second], snapshot)

    assert [(match.pattern_name, match.asset) for match in matches] == [
        ("a_pattern", "BTC"),
        ("a_pattern", "SOL"),
        ("b_pattern", "BTC"),
        ("b_pattern", "SOL"),
    ]


def test_critical_pattern_can_match() -> None:
    """Critical severity should not change matching semantics."""
    match = evaluate_patterns([_pattern(severity="CRITICAL")], _snapshot())[0]

    assert match.severity == "CRITICAL"


def test_one_pattern_exception_does_not_break_others(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """One failed pattern evaluation should be logged while others continue."""
    import duzman.patterns.evaluation as evaluation_module

    original = evaluation_module._evaluate_pattern_for_asset

    def fail_one(
        pattern: PatternDefinition,
        asset: str,
        snapshot: MetricsSnapshot,
    ) -> PatternMatch | None:
        if pattern.name == "bad_pattern":
            raise RuntimeError("broken pattern")
        return original(pattern, asset, snapshot)

    monkeypatch.setattr(evaluation_module, "_evaluate_pattern_for_asset", fail_one)

    with caplog.at_level(logging.WARNING):
        matches = evaluate_patterns(
            [_pattern(name="bad_pattern"), _pattern(name="good_pattern")],
            _snapshot(),
        )

    assert [match.pattern_name for match in matches] == ["good_pattern"]
    assert "pattern_evaluation_failed" in caplog.text
    assert "pattern_name=bad_pattern" in caplog.text


def test_nested_all_groups() -> None:
    """Nested all condition groups should evaluate recursively."""
    pattern = PatternDefinition(
        name="nested_pattern",
        display_name="Nested",
        severity="INFO",
        applies_to=["BTC"],
        conditions=ConditionGroup(
            all=[
                ConditionGroup(
                    all=[
                        _condition("RSI_4h", ">", 60),
                        _condition("funding_rate_avg", ">", 0.01),
                    ]
                ),
                _condition("price_change_24h_pct", ">", 1),
            ]
        ),
    )
    snapshot = _snapshot(
        asset_values={
            "BTC": {
                "RSI_4h": 65.0,
                "funding_rate_avg": 0.02,
                "price_change_24h_pct": 3.0,
            }
        }
    )

    assert len(evaluate_patterns([pattern], snapshot)) == 1


def _matches(condition: Condition) -> bool:
    """Return whether a one-condition test pattern matches."""
    return len(evaluate_patterns([_pattern(conditions=[condition])], _snapshot())) == 1


def _pattern(
    name: str = "test_pattern",
    severity: str = "INFO",
    applies_to: list[str] | None = None,
    conditions: list[Condition | ConditionGroup] | None = None,
) -> PatternDefinition:
    """Build a pattern definition for tests."""
    return PatternDefinition(
        name=name,
        display_name=name,
        severity=severity,
        applies_to=applies_to or ["BTC"],
        conditions=ConditionGroup(
            all=conditions
            or [
                _condition("RSI_4h", ">", 60),
                _condition("funding_rate_avg", ">", 0.01),
            ]
        ),
    )


def _condition(metric: str, operator: str, value: float | int) -> Condition:
    """Build a scalar threshold condition for tests."""
    return Condition(metric=metric, operator=operator, value=value)


def _snapshot(
    asset_values: dict[str, dict[str, float | None]] | None = None,
    global_metrics: dict[str, float | None] | None = None,
) -> MetricsSnapshot:
    """Build a metrics snapshot for tests."""
    values_by_asset = asset_values or {"BTC": {"RSI_4h": 65.0, "funding_rate_avg": 0.02}}
    return MetricsSnapshot(
        built_at=BUILT_AT,
        assets={
            asset: AssetMetrics(asset=asset, values=values)
            for asset, values in values_by_asset.items()
        },
        global_metrics={
            "fear_greed_index": None,
            "btc_dominance": None,
            "btc_dominance_change_7d_pct": None,
            **(global_metrics or {}),
        },
    )
