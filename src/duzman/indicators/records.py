"""Normalized indicator records for Stage A deterministic metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class IndicatorRecord:
    """Normalized indicator value matching the indicators table shape."""

    ts: datetime
    asset: str
    indicator_type: str
    timeframe: str
    value: Decimal
    parameters: dict[str, Any]
