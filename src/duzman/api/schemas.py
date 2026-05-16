"""Read-only API response schemas for persisted public market data."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


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


class IngestionStatusSummary(BaseModel):
    """Read-only summary of persisted ingestion and source health state."""

    latest_price_snapshot_at: datetime | None
    latest_source_health_check_at: datetime | None
    price_snapshot_count: int
    source_health_check_count: int
    sources_seen: list[str]
    symbols_seen: list[str]
