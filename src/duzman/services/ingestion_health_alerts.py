"""Deterministic read-only alerts for local market data ingestion health."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol


DEFAULT_PRICE_SNAPSHOT_FRESHNESS_THRESHOLD = timedelta(minutes=30)
DEFAULT_SOURCE_HEALTH_FRESHNESS_THRESHOLD = timedelta(minutes=30)
HEALTHY_SOURCE_STATUS = "ok"


class PriceSnapshotHealthRow(Protocol):
    """Read-only shape needed from a persisted public price snapshot."""

    source: str
    symbol: str
    collected_at: datetime


class SourceHealthCheckHealthRow(Protocol):
    """Read-only shape needed from a persisted source health check."""

    source: str
    status: str
    checked_at: datetime


@dataclass(frozen=True)
class IngestionHealthAlert:
    """Deterministic operator-facing alert derived from persisted local rows."""

    alert_type: str
    severity: str
    title: str
    message: str
    source: str | None = None
    symbol: str | None = None
    observed_at: datetime | None = None
    details: dict[str, object] | None = None


def evaluate_ingestion_health_alerts(
    price_snapshots: list[PriceSnapshotHealthRow],
    source_health_checks: list[SourceHealthCheckHealthRow],
    now: datetime | None = None,
    price_snapshot_freshness_threshold: timedelta = DEFAULT_PRICE_SNAPSHOT_FRESHNESS_THRESHOLD,
    source_health_freshness_threshold: timedelta = DEFAULT_SOURCE_HEALTH_FRESHNESS_THRESHOLD,
) -> list[IngestionHealthAlert]:
    """Return deterministic ingestion health alerts from already persisted rows."""
    checked_at = now or datetime.now(timezone.utc)
    alerts: list[IngestionHealthAlert] = []

    alerts.extend(
        _price_snapshot_alerts(
            price_snapshots=price_snapshots,
            now=checked_at,
            freshness_threshold=price_snapshot_freshness_threshold,
        )
    )
    alerts.extend(
        _source_health_alerts(
            source_health_checks=source_health_checks,
            now=checked_at,
            freshness_threshold=source_health_freshness_threshold,
        )
    )
    return alerts


def _price_snapshot_alerts(
    price_snapshots: list[PriceSnapshotHealthRow],
    now: datetime,
    freshness_threshold: timedelta,
) -> list[IngestionHealthAlert]:
    if not price_snapshots:
        return [
            IngestionHealthAlert(
                alert_type="no_price_snapshots",
                severity="critical",
                title="No price snapshots",
                message=(
                    "No persisted price snapshots are available for the read-only "
                    "market data API."
                ),
                details={"expected_table": "price_snapshots"},
            )
        ]

    latest_snapshot = max(price_snapshots, key=lambda row: row.collected_at)
    age = now - _as_aware_utc(latest_snapshot.collected_at)
    if age <= freshness_threshold:
        return []

    return [
        IngestionHealthAlert(
            alert_type="stale_price_snapshot",
            severity="warning",
            title="Latest price snapshot is stale",
            message=(
                "The latest persisted price snapshot is older than the configured "
                "freshness threshold."
            ),
            source=latest_snapshot.source,
            symbol=latest_snapshot.symbol,
            observed_at=latest_snapshot.collected_at,
            details=_age_details(age=age, threshold=freshness_threshold),
        )
    ]


def _source_health_alerts(
    source_health_checks: list[SourceHealthCheckHealthRow],
    now: datetime,
    freshness_threshold: timedelta,
) -> list[IngestionHealthAlert]:
    if not source_health_checks:
        return [
            IngestionHealthAlert(
                alert_type="no_source_health_checks",
                severity="warning",
                title="No source health checks",
                message=(
                    "No persisted source health checks are available for public "
                    "market data sources."
                ),
                details={"expected_table": "source_health_checks"},
            )
        ]

    alerts: list[IngestionHealthAlert] = []
    latest_check = max(source_health_checks, key=lambda row: row.checked_at)
    latest_age = now - _as_aware_utc(latest_check.checked_at)
    if latest_age > freshness_threshold:
        alerts.append(
            IngestionHealthAlert(
                alert_type="stale_source_health",
                severity="warning",
                title="Latest source health check is stale",
                message=(
                    "The latest persisted source health check is older than the "
                    "configured freshness threshold."
                ),
                source=latest_check.source,
                observed_at=latest_check.checked_at,
                details=_age_details(age=latest_age, threshold=freshness_threshold),
            )
        )

    for health_check in source_health_checks:
        status = health_check.status.lower()
        age = now - _as_aware_utc(health_check.checked_at)
        if status == HEALTHY_SOURCE_STATUS or age > freshness_threshold:
            continue
        alerts.append(
            IngestionHealthAlert(
                alert_type="source_recent_failure",
                severity="critical" if status == "failed" else "warning",
                title="Recent source health failure",
                message=(
                    "A recent persisted source health check reports an unhealthy "
                    "public market data source."
                ),
                source=health_check.source,
                observed_at=health_check.checked_at,
                details={
                    "status": health_check.status,
                    **_age_details(age, freshness_threshold),
                },
            )
        )

    return alerts


def _age_details(age: timedelta, threshold: timedelta) -> dict[str, int]:
    return {
        "age_minutes": max(0, int(age.total_seconds() // 60)),
        "threshold_minutes": int(threshold.total_seconds() // 60),
    }


def _as_aware_utc(timestamp: datetime) -> datetime:
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone(timezone.utc)
