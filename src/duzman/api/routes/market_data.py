"""Read-only FastAPI routes for persisted public market data."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from duzman.api.dependencies import get_api_db
from duzman.api.schemas import (
    IngestionStatusSummary,
    PriceSnapshotRead,
    SourceHealthRead,
)
from duzman.db.models import PriceSnapshot, SourceHealthCheck
from duzman.logging_config import safe_error_message
from duzman.repositories import PriceSnapshotRepository, SourceHealthRepository


router = APIRouter(prefix="/api/market-data", tags=["market-data"])


@router.get("/prices/latest", response_model=list[PriceSnapshotRead])
def list_latest_price_snapshots(
    db: Annotated[Session, Depends(get_api_db)],
    symbol: Annotated[str | None, Query(max_length=10)] = None,
    source: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PriceSnapshotRead]:
    """Return latest persisted public price snapshots without collecting data."""
    repository = PriceSnapshotRepository(db)
    return [
        _price_snapshot_response(snapshot)
        for snapshot in repository.list_latest(
            symbol=symbol,
            source=source,
            limit=limit,
        )
    ]


@router.get("/source-health", response_model=list[SourceHealthRead])
def list_latest_source_health(
    db: Annotated[Session, Depends(get_api_db)],
    source: Annotated[str | None, Query(max_length=20)] = None,
) -> list[SourceHealthRead]:
    """Return latest persisted source health checks without contacting sources."""
    repository = SourceHealthRepository(db)
    return [
        _source_health_response(health_check)
        for health_check in repository.list_latest(source=source)
    ]


@router.get("/ingestion-status", response_model=IngestionStatusSummary)
def get_ingestion_status_summary(
    db: Annotated[Session, Depends(get_api_db)],
) -> IngestionStatusSummary:
    """Return a read-only summary of persisted ingestion state."""
    latest_price_snapshot_at = db.scalar(select(func.max(PriceSnapshot.collected_at)))
    latest_source_health_check_at = db.scalar(
        select(func.max(SourceHealthCheck.checked_at))
    )
    price_snapshot_count = db.scalar(
        select(func.count()).select_from(PriceSnapshot)
    )
    source_health_check_count = db.scalar(
        select(func.count()).select_from(SourceHealthCheck)
    )
    price_sources = set(db.scalars(select(PriceSnapshot.source).distinct()))
    health_sources = set(db.scalars(select(SourceHealthCheck.source).distinct()))
    sources_seen = sorted(price_sources | health_sources)
    symbols_seen = sorted(
        symbol
        for symbol in db.scalars(select(PriceSnapshot.symbol).distinct())
    )

    return IngestionStatusSummary(
        latest_price_snapshot_at=latest_price_snapshot_at,
        latest_source_health_check_at=latest_source_health_check_at,
        price_snapshot_count=price_snapshot_count or 0,
        source_health_check_count=source_health_check_count or 0,
        sources_seen=sources_seen,
        symbols_seen=symbols_seen,
    )


def _price_snapshot_response(snapshot: PriceSnapshot) -> PriceSnapshotRead:
    return PriceSnapshotRead(
        symbol=snapshot.symbol,
        source=snapshot.source,
        quote_currency=snapshot.quote_currency,
        price=snapshot.price,
        collected_at=snapshot.collected_at,
        created_at=snapshot.created_at,
        volume_24h_quote=snapshot.volume_24h_quote,
        price_change_24h_pct=snapshot.price_change_24h_pct,
    )


def _source_health_response(health_check: SourceHealthCheck) -> SourceHealthRead:
    return SourceHealthRead(
        source=health_check.source,
        status=health_check.status,
        checked_at=health_check.checked_at,
        created_at=health_check.created_at,
        latency_ms=health_check.latency_ms,
        error_message=safe_error_message(health_check.error_message)
        if health_check.error_message
        else None,
    )
