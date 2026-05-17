"""Evaluate deterministic Pattern Engine definitions against metric snapshots."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict

from duzman.logging_config import get_logger, log_event, safe_error_message
from duzman.patterns.models import Condition, ConditionGroup, PatternDefinition
from duzman.patterns.snapshot import GLOBAL_METRICS, MetricsSnapshot

LOGGER = get_logger(__name__)
MetricValue = float | int | None
MetricValues = dict[str, MetricValue | str]


class PatternMatch(BaseModel):
    """Pattern trigger candidate produced by deterministic evaluation."""

    pattern_name: str
    asset: str
    severity: str
    evaluated_at: datetime
    conditions_snapshot: dict[str, float | int]
    model_config = ConfigDict(extra="forbid", frozen=True)


def evaluate_patterns(
    patterns: list[PatternDefinition],
    snapshot: MetricsSnapshot,
) -> list[PatternMatch]:
    """Evaluate patterns against a metrics snapshot and return stable matches."""
    matches: list[PatternMatch] = []
    for pattern in sorted(patterns, key=lambda item: item.name):
        for asset in sorted(snapshot.assets):
            if asset not in pattern.applies_to:
                continue
            try:
                match = _evaluate_pattern_for_asset(pattern, asset, snapshot)
            except Exception as exc:  # noqa: BLE001 - one bad pattern must not stop others.
                log_event(
                    LOGGER,
                    "pattern_evaluation_failed",
                    level=logging.WARNING,
                    pattern_name=pattern.name,
                    asset=asset,
                    error=safe_error_message(exc),
                )
                continue
            if match is not None:
                matches.append(match)
    return sorted(matches, key=lambda item: (item.pattern_name, item.asset))


def _evaluate_pattern_for_asset(
    pattern: PatternDefinition,
    asset: str,
    snapshot: MetricsSnapshot,
) -> PatternMatch | None:
    """Evaluate one pattern for one asset."""
    if asset not in pattern.applies_to:
        return None

    metric_names = _collect_metric_names(pattern.conditions)
    resolved_values = {
        metric_name: _resolve_metric_value(metric_name, asset, snapshot)
        for metric_name in metric_names
    }
    if any(value is None for value in resolved_values.values()):
        return None

    metric_values: MetricValues = {
        **resolved_values,
        "__asset__": asset,
        "__pattern_name__": pattern.name,
    }
    if not _evaluate_condition_group(pattern.conditions, metric_values):
        return None

    return PatternMatch(
        pattern_name=pattern.name,
        asset=asset,
        severity=pattern.severity,
        evaluated_at=_ensure_utc(snapshot.built_at),
        conditions_snapshot={
            metric_name: resolved_values[metric_name]
            for metric_name in sorted(metric_names)
            if resolved_values[metric_name] is not None
        },
    )


def _evaluate_condition_group(group: ConditionGroup, metric_values: MetricValues) -> bool:
    """Evaluate a recursive condition group using AND or OR semantics."""
    asset = str(metric_values["__asset__"])
    if group.all_ is not None:
        return all(
            _evaluate_condition_node(node, metric_values, asset)
            for node in group.all_
        )
    if group.any_ is not None:
        return any(
            _evaluate_condition_node(node, metric_values, asset)
            for node in group.any_
        )
    return False


def _evaluate_single_condition(
    condition: Condition,
    metric_values: MetricValues,
    asset: str,
) -> bool:
    """Evaluate one metric condition for one asset."""
    lhs = metric_values.get(condition.metric)
    if not isinstance(lhs, (float, int)):
        return False
    rhs = _resolve_threshold(condition, asset)
    if rhs is None:
        log_event(
            LOGGER,
            "pattern_misconfigured",
            level=logging.WARNING,
            pattern_name=metric_values.get("__pattern_name__"),
            asset=asset,
            metric_name=condition.metric,
        )
        return False

    lhs_value = float(lhs)
    rhs_value = float(rhs)
    if condition.operator == ">":
        return lhs_value > rhs_value
    if condition.operator == "<":
        return lhs_value < rhs_value
    if condition.operator == ">=":
        return lhs_value >= rhs_value
    if condition.operator == "<=":
        return lhs_value <= rhs_value
    if condition.operator == "==":
        return lhs_value == rhs_value
    if condition.operator == "!=":
        return lhs_value != rhs_value
    return False


def _resolve_metric_value(
    metric_name: str,
    asset: str,
    snapshot: MetricsSnapshot,
) -> float | int | None:
    """Resolve a metric value from global or per-asset snapshot values."""
    if metric_name in GLOBAL_METRICS:
        return snapshot.global_metrics.get(metric_name)
    asset_metrics = snapshot.assets.get(asset)
    if asset_metrics is None:
        return None
    return asset_metrics.values.get(metric_name)


def _resolve_threshold(condition: Condition, asset: str) -> float | int | None:
    """Resolve the threshold for a condition and asset."""
    if condition.per_asset_thresholds is not None:
        return condition.per_asset_thresholds.get(asset)
    return condition.value


def _evaluate_condition_node(
    node: Condition | ConditionGroup,
    metric_values: MetricValues,
    asset: str,
) -> bool:
    """Evaluate a condition or nested condition group."""
    if isinstance(node, ConditionGroup):
        return _evaluate_condition_group(node, metric_values)
    return _evaluate_single_condition(node, metric_values, asset)


def _collect_metric_names(group: ConditionGroup) -> set[str]:
    """Collect all metric names referenced by a condition group."""
    nodes = group.all_ if group.all_ is not None else group.any_
    if nodes is None:
        return set()
    metric_names: set[str] = set()
    for node in nodes:
        if isinstance(node, ConditionGroup):
            metric_names.update(_collect_metric_names(node))
        else:
            metric_names.add(node.metric)
    return metric_names


def _ensure_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime for the match timestamp."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
