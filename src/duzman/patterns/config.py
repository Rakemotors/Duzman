"""Load and validate deterministic Pattern Engine YAML configuration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from duzman.logging_config import get_logger, log_event
from duzman.patterns.known_metrics import KNOWN_METRICS, KNOWN_OPERATORS
from duzman.patterns.models import Condition, ConditionGroup, PatternDefinition


STAGE_A_ASSETS: frozenset[str] = frozenset({"BTC", "ETH", "SOL", "SUI", "TON", "UNI"})


class PatternConfigError(Exception):
    """Controlled pattern configuration validation error."""

    def __init__(self, field_path: str, reason: str) -> None:
        self.field_path = field_path
        self.reason = reason
        super().__init__(f"{field_path}: {reason}")


def load_patterns(path: Path) -> list[PatternDefinition]:
    """Load and validate Pattern Engine definitions from a YAML file."""
    resolved_path = path.resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(resolved_path)

    payload = yaml.safe_load(resolved_path.read_text(encoding="utf-8"))
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise PatternConfigError("patterns", "top-level YAML document must be a mapping")
    patterns_payload = payload.get("patterns")
    if patterns_payload is None:
        raise PatternConfigError("patterns", "required key is missing")
    if not isinstance(patterns_payload, list):
        raise PatternConfigError("patterns", "must be a list")

    definitions = [
        _validate_pattern_payload(index, pattern_payload)
        for index, pattern_payload in enumerate(patterns_payload)
    ]
    _validate_unique_names(definitions)
    for index, definition in enumerate(definitions):
        _validate_pattern_semantics(index, definition)

    log_event(
        get_logger(__name__),
        "patterns_loaded",
        level=logging.INFO,
        count=len(definitions),
        path=str(resolved_path),
    )
    return definitions


def _validate_pattern_payload(
    index: int,
    pattern_payload: Any,
) -> PatternDefinition:
    try:
        return PatternDefinition.model_validate(pattern_payload)
    except ValidationError as exc:
        error = exc.errors()[0]
        reason = str(error["msg"])
        if "input" in error:
            reason = f"{reason}; input={error['input']}"
        raise PatternConfigError(
            _field_path(("patterns", index, *error["loc"])),
            reason,
        ) from exc


def _validate_unique_names(definitions: list[PatternDefinition]) -> None:
    seen_names: set[str] = set()
    for index, definition in enumerate(definitions):
        if definition.name in seen_names:
            raise PatternConfigError(
                f"patterns[{index}].name",
                f"duplicate pattern name {definition.name}",
            )
        seen_names.add(definition.name)


def _validate_pattern_semantics(
    index: int,
    definition: PatternDefinition,
) -> None:
    for asset_index, asset in enumerate(definition.applies_to):
        if asset not in STAGE_A_ASSETS:
            raise PatternConfigError(
                f"patterns[{index}].applies_to[{asset_index}]",
                f"unknown asset {asset}",
            )
    _validate_condition_group(
        definition.conditions,
        ("patterns", index, "conditions"),
        frozenset(definition.applies_to),
    )


def _validate_condition_group(
    group: ConditionGroup,
    path: tuple[str | int, ...],
    applies_to: frozenset[str],
) -> None:
    nodes = group.all_ if group.all_ is not None else group.any_
    field_name = "all" if group.all_ is not None else "any"
    if nodes is None:
        raise PatternConfigError(_field_path(path), "condition group is empty")

    for index, node in enumerate(nodes):
        node_path = (*path, field_name, index)
        if isinstance(node, ConditionGroup):
            _validate_condition_group(node, node_path, applies_to)
        else:
            _validate_condition(node, node_path, applies_to)


def _validate_condition(
    condition: Condition,
    path: tuple[str | int, ...],
    applies_to: frozenset[str],
) -> None:
    if condition.metric not in KNOWN_METRICS:
        raise PatternConfigError(
            _field_path((*path, "metric")),
            f"unknown metric {condition.metric}",
        )
    if condition.operator not in KNOWN_OPERATORS:
        raise PatternConfigError(
            _field_path((*path, "operator")),
            f"unknown operator {condition.operator}",
        )
    if condition.per_asset_thresholds is not None:
        _validate_per_asset_thresholds(condition, path, applies_to)


def _validate_per_asset_thresholds(
    condition: Condition,
    path: tuple[str | int, ...],
    applies_to: frozenset[str],
) -> None:
    assert condition.per_asset_thresholds is not None
    for asset in condition.per_asset_thresholds:
        if asset not in STAGE_A_ASSETS:
            raise PatternConfigError(
                _field_path((*path, "per_asset_thresholds", asset)),
                f"unknown asset {asset}",
            )
        if asset not in applies_to:
            raise PatternConfigError(
                _field_path((*path, "per_asset_thresholds", asset)),
                f"asset {asset} is not listed in applies_to",
            )


def _field_path(parts: tuple[str | int, ...]) -> str:
    rendered = ""
    for part in parts:
        if isinstance(part, int):
            rendered += f"[{part}]"
        elif not rendered:
            rendered = part
        else:
            rendered += f".{part}"
    return rendered
