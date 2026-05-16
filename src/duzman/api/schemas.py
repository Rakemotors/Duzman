"""Read-only API response schemas for persisted public market data."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


JsonScalar = str | int | float | bool | None


class PriceSnapshotRead(BaseModel):
    """Read-only representation of a persisted public price snapshot."""

    symbol: str
    source: str
    quote_currency: str
    price: Decimal
    collected_at: datetime
    created_at: datetime
    volume_24h_quote: Decimal | None = None
    price_change_24h_pct: Decimal | None = None


class SourceHealthRead(BaseModel):
    """Read-only representation of the latest public source health check."""

    source: str
    status: str
    checked_at: datetime
    created_at: datetime
    latency_ms: int | None = None
    error_message: str | None = None


class IngestionHealthAlertRead(BaseModel):
    """Read-only deterministic alert for persisted ingestion health."""

    alert_type: str
    severity: str
    title: str
    message: str
    source: str | None = None
    symbol: str | None = None
    observed_at: datetime | None = None
    details: dict[str, JsonScalar] | None = None


class IngestionHealthSummaryRead(BaseModel):
    """Compact deterministic summary of persisted ingestion health."""

    status: str
    alert_count: int
    highest_severity: str | None
    latest_checked_at: datetime | None
    critical_alert_count: int
    warning_alert_count: int


class IngestionStatusSummary(BaseModel):
    """Read-only summary of persisted ingestion and source health state."""

    latest_price_snapshot_at: datetime | None
    latest_source_health_check_at: datetime | None
    price_snapshot_count: int
    source_health_check_count: int
    sources_seen: list[str]
    symbols_seen: list[str]
    ingestion_health_summary: IngestionHealthSummaryRead
