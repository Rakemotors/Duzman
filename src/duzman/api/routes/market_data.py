"""Read-only FastAPI routes for persisted public market data."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from duzman.api.dependencies import get_api_db, require_api_key
from duzman.api.schemas import (
    IngestionHealthAlertRead,
    IngestionHealthSummaryRead,
    IngestionStatusSummary,
    PriceSnapshotRead,
    SourceHealthRead,
)
from duzman.db.models import PriceSnapshot, SourceHealthCheck
from duzman.logging_config import safe_error_message
from duzman.repositories import PriceSnapshotRepository, SourceHealthRepository
from duzman.services import (
    IngestionHealthAlert,
    IngestionHealthSummary,
    evaluate_ingestion_health_alerts,
    summarize_ingestion_health,
)

router = APIRouter(
    prefix="/api/market-data",
    tags=["market-data"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/prices/latest", response_model=list[PriceSnapshotRead])
def list_latest_price_snapshots(
    db: Annotated[Session, Depends(get_api_db)],
    asset: Annotated[str | None, Query(max_length=10)] = None,
    source: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[PriceSnapshotRead]:
    """Return latest persisted public price snapshots without collecting data."""
    repository = PriceSnapshotRepository(db)
    return [
        _price_snapshot_response(snapshot)
        for snapshot in repository.list_latest(
            asset=asset,
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
    latest_price_snapshot_at = db.scalar(select(func.max(PriceSnapshot.ts)))
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
    assets_seen = sorted(
        asset
        for asset in db.scalars(select(PriceSnapshot.asset).distinct())
    )
    price_repository = PriceSnapshotRepository(db)
    health_repository = SourceHealthRepository(db)
    alerts = _evaluate_ingestion_alerts(
        price_repository=price_repository,
        health_repository=health_repository,
    )
    latest_checked_at = _latest_timestamp(
        latest_price_snapshot_at,
        latest_source_health_check_at,
    )

    return IngestionStatusSummary(
        latest_price_snapshot_at=latest_price_snapshot_at,
        latest_source_health_check_at=latest_source_health_check_at,
        price_snapshot_count=price_snapshot_count or 0,
        source_health_check_count=source_health_check_count or 0,
        sources_seen=sources_seen,
        assets_seen=assets_seen,
        ingestion_health_summary=_ingestion_health_summary_response(
            summarize_ingestion_health(
                alerts=alerts,
                latest_checked_at=latest_checked_at,
            )
        ),
    )


@router.get("/ingestion-alerts", response_model=list[IngestionHealthAlertRead])
def list_ingestion_health_alerts(
    db: Annotated[Session, Depends(get_api_db)],
) -> list[IngestionHealthAlertRead]:
    """Return deterministic read-only alerts for persisted ingestion health."""
    price_repository = PriceSnapshotRepository(db)
    health_repository = SourceHealthRepository(db)
    alerts = _evaluate_ingestion_alerts(
        price_repository=price_repository,
        health_repository=health_repository,
    )
    return [_ingestion_health_alert_response(alert) for alert in alerts]


def _price_snapshot_response(snapshot: PriceSnapshot) -> PriceSnapshotRead:
    return PriceSnapshotRead(
        asset=snapshot.asset,
        source=snapshot.source,
        quote_currency=snapshot.quote_currency,
        price_usd=snapshot.price_usd,
        ts=snapshot.ts,
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


def _ingestion_health_alert_response(
    alert: IngestionHealthAlert,
) -> IngestionHealthAlertRead:
    return IngestionHealthAlertRead(
        alert_type=alert.alert_type,
        severity=alert.severity,
        title=alert.title,
        message=alert.message,
        source=alert.source,
        asset=alert.asset,
        observed_at=alert.observed_at,
        details=alert.details,
    )


def _ingestion_health_summary_response(
    summary: IngestionHealthSummary,
) -> IngestionHealthSummaryRead:
    return IngestionHealthSummaryRead(
        status=summary.status,
        alert_count=summary.alert_count,
        highest_severity=summary.highest_severity,
        latest_checked_at=summary.latest_checked_at,
        critical_alert_count=summary.critical_alert_count,
        warning_alert_count=summary.warning_alert_count,
    )


def _evaluate_ingestion_alerts(
    price_repository: PriceSnapshotRepository,
    health_repository: SourceHealthRepository,
) -> list[IngestionHealthAlert]:
    return evaluate_ingestion_health_alerts(
        price_snapshots=price_repository.list_latest(limit=1),
        source_health_checks=health_repository.list_latest(),
    )


def _latest_timestamp(*timestamps: datetime | None) -> datetime | None:
    available_timestamps = [timestamp for timestamp in timestamps if timestamp]
    return max(available_timestamps) if available_timestamps else None
