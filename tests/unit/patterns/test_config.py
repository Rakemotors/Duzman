"""Tests for Pattern Engine YAML configuration loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from duzman.patterns.config import PatternConfigError, load_patterns


def write_patterns_yaml(tmp_path: Path, text: str) -> Path:
    """Write a temporary pattern YAML file for loader tests."""
    path = tmp_path / "patterns.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def valid_pattern_yaml(extra_body: str = "cooldown_hours: 6") -> str:
    """Return one valid pattern definition with an overridable body fragment."""
    return f"""
patterns:
  - name: leveraged_long_buildup
    display_name: "Лонги накапливаются на росте"
    severity: WARNING
    applies_to: [BTC, ETH, SOL]
    {extra_body}
    conditions:
      all:
        - metric: RSI_4h
          operator: ">"
          value: 65
        - metric: funding_rate_avg
          operator: ">"
          value: 0.03
"""


def test_load_valid_yaml(tmp_path: Path) -> None:
    """A minimal valid YAML file should load into immutable pattern models."""
    patterns = load_patterns(write_patterns_yaml(tmp_path, valid_pattern_yaml()))

    assert len(patterns) == 1
    assert patterns[0].name == "leveraged_long_buildup"
    assert patterns[0].severity == "WARNING"


def test_load_all_10_appendix_a() -> None:
    """The committed Appendix A configuration should contain 10 unique patterns."""
    patterns = load_patterns(Path("config/patterns.yaml"))

    assert len(patterns) == 10
    assert len({pattern.name for pattern in patterns}) == 10


def test_default_cooldown_2h(tmp_path: Path) -> None:
    """Omitted cooldown_hours should default to 2.0 hours."""
    patterns = load_patterns(write_patterns_yaml(tmp_path, valid_pattern_yaml("")))

    assert patterns[0].cooldown_hours == 2.0


def test_unknown_metric_rejected(tmp_path: Path) -> None:
    """Unknown metric names should fail with an indexed field path."""
    path = write_patterns_yaml(
        tmp_path,
        valid_pattern_yaml().replace("RSI_4h", "FAKE_METRIC"),
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert "FAKE_METRIC" in str(exc_info.value)
    assert exc_info.value.field_path == "patterns[0].conditions.all[0].metric"


def test_unknown_operator_rejected(tmp_path: Path) -> None:
    """Unknown condition operators should be rejected."""
    path = write_patterns_yaml(tmp_path, valid_pattern_yaml().replace('">"', '"~~"'))

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert "~~" in str(exc_info.value)
    assert exc_info.value.field_path == "patterns[0].conditions.all[0].operator"


def test_unknown_severity_rejected(tmp_path: Path) -> None:
    """Unknown severity values should be rejected by the schema."""
    path = write_patterns_yaml(tmp_path, valid_pattern_yaml().replace("WARNING", "URGENT"))

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert exc_info.value.field_path == "patterns[0].severity"
    assert "URGENT" in str(exc_info.value)


def test_unknown_asset_rejected(tmp_path: Path) -> None:
    """Unknown applies_to assets should be rejected."""
    path = write_patterns_yaml(
        tmp_path,
        valid_pattern_yaml().replace("[BTC, ETH, SOL]", "[BTC, XRP]"),
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert exc_info.value.field_path == "patterns[0].applies_to[1]"
    assert "XRP" in str(exc_info.value)


def test_duplicate_name_rejected(tmp_path: Path) -> None:
    """Duplicate pattern names should fail before engine evaluation."""
    path = write_patterns_yaml(
        tmp_path,
        valid_pattern_yaml()
        + """
  - name: leveraged_long_buildup
    display_name: "Duplicate"
    severity: INFO
    applies_to: [BTC]
    conditions:
      all:
        - metric: RSI_1h
          operator: ">"
          value: 50
""",
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert exc_info.value.field_path == "patterns[1].name"
    assert "duplicate" in exc_info.value.reason


def test_extra_field_rejected(tmp_path: Path) -> None:
    """Unexpected YAML fields should be rejected."""
    path = write_patterns_yaml(
        tmp_path,
        valid_pattern_yaml().replace("severity: WARNING", "severity: WARNING\n    author: Claude"),
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert exc_info.value.field_path == "patterns[0].author"


def test_nested_any_inside_all(tmp_path: Path) -> None:
    """Nested any groups inside all groups should parse recursively."""
    path = write_patterns_yaml(
        tmp_path,
        """
patterns:
  - name: nested_pattern
    display_name: "Nested"
    severity: INFO
    applies_to: [BTC]
    conditions:
      all:
        - any:
            - metric: RSI_1h
              operator: ">"
              value: 60
            - metric: RSI_4h
              operator: ">"
              value: 60
        - metric: funding_rate_avg
          operator: ">"
          value: 0.01
""",
    )

    patterns = load_patterns(path)

    assert patterns[0].conditions.all_[0].any_ is not None


def test_empty_patterns_file(tmp_path: Path) -> None:
    """An empty patterns list is valid and returns an empty list."""
    path = write_patterns_yaml(tmp_path, "patterns: []\n")

    assert load_patterns(path) == []


def test_file_not_found(tmp_path: Path) -> None:
    """Missing YAML files should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_patterns(tmp_path / "missing.yaml")


def test_per_asset_thresholds_valid(tmp_path: Path) -> None:
    """Per-asset thresholds should parse when keys match applies_to."""
    path = write_patterns_yaml(
        tmp_path,
        """
patterns:
  - name: etf_accumulation_strong
    display_name: "ETF"
    severity: INFO
    applies_to: [BTC, ETH]
    conditions:
      all:
        - metric: etf_cum_flow_5d_usd
          operator: ">"
          per_asset_thresholds:
            BTC: 1000000000
            ETH: 200000000
""",
    )

    patterns = load_patterns(path)

    condition = patterns[0].conditions.all_[0]
    assert condition.per_asset_thresholds == {"BTC": 1000000000.0, "ETH": 200000000.0}


def test_per_asset_thresholds_key_not_in_applies_to(tmp_path: Path) -> None:
    """Per-asset thresholds may only reference assets listed in applies_to."""
    path = write_patterns_yaml(
        tmp_path,
        """
patterns:
  - name: etf_accumulation_strong
    display_name: "ETF"
    severity: INFO
    applies_to: [BTC, ETH]
    conditions:
      all:
        - metric: etf_cum_flow_5d_usd
          operator: ">"
          per_asset_thresholds:
            BTC: 1000000000
            SOL: 200000000
""",
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert exc_info.value.field_path == (
        "patterns[0].conditions.all[0].per_asset_thresholds.SOL"
    )


def test_value_and_per_asset_thresholds_both_set(tmp_path: Path) -> None:
    """A condition cannot define both scalar and per-asset thresholds."""
    path = write_patterns_yaml(
        tmp_path,
        """
patterns:
  - name: invalid_thresholds
    display_name: "Invalid"
    severity: INFO
    applies_to: [BTC]
    conditions:
      all:
        - metric: etf_cum_flow_5d_usd
          operator: ">"
          value: 100
          per_asset_thresholds:
            BTC: 1000000000
""",
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert "exactly one of value or per_asset_thresholds" in str(exc_info.value)


def test_value_and_per_asset_thresholds_both_none(tmp_path: Path) -> None:
    """A condition must define a scalar or per-asset threshold."""
    path = write_patterns_yaml(
        tmp_path,
        """
patterns:
  - name: invalid_thresholds
    display_name: "Invalid"
    severity: INFO
    applies_to: [BTC]
    conditions:
      all:
        - metric: RSI_1h
          operator: ">"
""",
    )

    with pytest.raises(PatternConfigError) as exc_info:
        load_patterns(path)

    assert "exactly one of value or per_asset_thresholds" in str(exc_info.value)
