"""Pydantic models for deterministic Pattern Engine configuration."""

from __future__ import annotations

import re
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Condition(BaseModel):
    """Single deterministic metric comparison from pattern configuration."""

    metric: str
    operator: str
    value: float | int | None = None
    per_asset_thresholds: dict[str, float] | None = None

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_threshold_source(self) -> "Condition":
        """Require exactly one threshold source for a condition."""
        value_is_set = self.value is not None
        per_asset_is_set = self.per_asset_thresholds is not None
        if value_is_set == per_asset_is_set:
            raise ValueError(
                "exactly one of value or per_asset_thresholds must be provided"
            )
        return self


ConditionNode = Union[Condition, "ConditionGroup"]


class ConditionGroup(BaseModel):
    """Recursive group of conditions joined by either all or any semantics."""

    all_: list[ConditionNode] | None = Field(default=None, alias="all")
    any_: list[ConditionNode] | None = Field(default=None, alias="any")

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    @model_validator(mode="after")
    def validate_single_group_operator(self) -> "ConditionGroup":
        """Require exactly one boolean group operator."""
        all_is_set = self.all_ is not None
        any_is_set = self.any_ is not None
        if all_is_set == any_is_set:
            raise ValueError("exactly one of all or any must be provided")
        return self


class PatternDefinition(BaseModel):
    """Validated deterministic market-state pattern definition."""

    name: str
    display_name: str
    severity: Literal["INFO", "WARNING", "CRITICAL"]
    applies_to: list[str]
    conditions: ConditionGroup
    cooldown_hours: float = 2.0
    enabled: bool = True

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def validate_name_shape(self) -> "PatternDefinition":
        """Require stable snake_case pattern names for deduplication keys."""
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValueError("name must be snake_case")
        return self


ConditionGroup.model_rebuild()
