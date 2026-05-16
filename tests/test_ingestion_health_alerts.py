from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from duzman.services.ingestion_health_alerts import (
    IngestionHealthAlert,
    evaluate_ingestion_health_alerts,
    summarize_ingestion_health,
)


NOW = datetime(2026, 5, 16, 12, 0, tzinfo=timezone.utc)
FRESH_THRESHOLD = timedelta(minutes=30)


@dataclass(frozen=True)
class _PriceRow:
    source: str
    symbol: str
    collected_at: datetime


@dataclass(frozen=True)
class _HealthRow:
    source: str
    status: str
    checked_at: datetime


def test_no_price_snapshots_alert_is_emitted():
    """Empty price history should produce a deterministic operator alert."""
    alerts = evaluate_ingestion_health_alerts(
        price_snapshots=[],
        source_health_checks=[_HealthRow("binance", "ok", NOW - timedelta(minutes=5))],
        now=NOW,
        price_snapshot_freshness_threshold=FRESH_THRESHOLD,
        source_health_freshness_threshold=FRESH_THRESHOLD,
    )

    assert _alert_types(alerts) == {"no_price_snapshots"}


def test_stale_price_snapshot_alert_is_emitted():
    """Old latest prices should produce stale_price_snapshot."""
    alerts = evaluate_ingestion_health_alerts(
        price_snapshots=[_PriceRow("binance", "BTC", NOW - timedelta(minutes=45))],
        source_health_checks=[_HealthRow("binance", "ok", NOW - timedelta(minutes=5))],
        now=NOW,
        price_snapshot_freshness_threshold=FRESH_THRESHOLD,
        source_health_freshness_threshold=FRESH_THRESHOLD,
    )

    stale_alert = _only_alert_of_type(alerts, "stale_price_snapshot")
    assert stale_alert.source == "binance"
    assert stale_alert.symbol == "BTC"
    assert stale_alert.details == {"age_minutes": 45, "threshold_minutes": 30}


def test_fresh_price_snapshot_has_no_stale_price_alert():
    """Fresh latest prices should not produce stale_price_snapshot."""
    alerts = evaluate_ingestion_health_alerts(
        price_snapshots=[_PriceRow("binance", "BTC", NOW - timedelta(minutes=10))],
        source_health_checks=[_HealthRow("binance", "ok", NOW - timedelta(minutes=5))],
        now=NOW,
        price_snapshot_freshness_threshold=FRESH_THRESHOLD,
        source_health_freshness_threshold=FRESH_THRESHOLD,
    )

    assert "stale_price_snapshot" not in _alert_types(alerts)


def test_no_source_health_checks_alert_is_emitted():
    """Missing source health rows should produce a deterministic alert."""
    alerts = evaluate_ingestion_health_alerts(
        price_snapshots=[_PriceRow("binance", "BTC", NOW - timedelta(minutes=10))],
        source_health_checks=[],
        now=NOW,
        price_snapshot_freshness_threshold=FRESH_THRESHOLD,
        source_health_freshness_threshold=FRESH_THRESHOLD,
    )

    assert _alert_types(alerts) == {"no_source_health_checks"}


def test_recent_failed_source_health_alert_is_emitted():
    """Recent failed source health checks should produce source_recent_failure."""
    alerts = evaluate_ingestion_health_alerts(
        price_snapshots=[_PriceRow("binance", "BTC", NOW - timedelta(minutes=10))],
        source_health_checks=[
            _HealthRow("coingecko", "failed", NOW - timedelta(minutes=3))
        ],
        now=NOW,
        price_snapshot_freshness_threshold=FRESH_THRESHOLD,
        source_health_freshness_threshold=FRESH_THRESHOLD,
    )

    failure_alert = _only_alert_of_type(alerts, "source_recent_failure")
    assert failure_alert.severity == "critical"
    assert failure_alert.source == "coingecko"
    assert failure_alert.details == {
        "status": "failed",
        "age_minutes": 3,
        "threshold_minutes": 30,
    }


def test_stale_source_health_alert_is_emitted():
    """Old latest source health checks should produce stale_source_health."""
    alerts = evaluate_ingestion_health_alerts(
        price_snapshots=[_PriceRow("binance", "BTC", NOW - timedelta(minutes=10))],
        source_health_checks=[_HealthRow("binance", "ok", NOW - timedelta(minutes=90))],
        now=NOW,
        price_snapshot_freshness_threshold=FRESH_THRESHOLD,
        source_health_freshness_threshold=FRESH_THRESHOLD,
    )

    stale_alert = _only_alert_of_type(alerts, "stale_source_health")
    assert stale_alert.source == "binance"
    assert stale_alert.details == {"age_minutes": 90, "threshold_minutes": 30}


def test_all_healthy_and_fresh_returns_empty_alert_list():
    """Healthy fresh persisted rows should produce no ingestion health alerts."""
    alerts = evaluate_ingestion_health_alerts(
        price_snapshots=[_PriceRow("binance", "BTC", NOW - timedelta(minutes=10))],
        source_health_checks=[_HealthRow("binance", "ok", NOW - timedelta(minutes=5))],
        now=NOW,
        price_snapshot_freshness_threshold=FRESH_THRESHOLD,
        source_health_freshness_threshold=FRESH_THRESHOLD,
    )

    assert alerts == []


def test_ingestion_health_summary_is_healthy_without_alerts():
    """No alerts should summarize to healthy with no highest severity."""
    summary = summarize_ingestion_health(
        alerts=[],
        latest_checked_at=NOW,
    )

    assert summary.status == "healthy"
    assert summary.alert_count == 0
    assert summary.highest_severity is None
    assert summary.latest_checked_at == NOW
    assert summary.critical_alert_count == 0
    assert summary.warning_alert_count == 0


def test_ingestion_health_summary_is_warning_for_warning_alerts():
    """Warning-only alerts should summarize to warning."""
    summary = summarize_ingestion_health(
        alerts=[
            IngestionHealthAlert(
                alert_type="stale_price_snapshot",
                severity="warning",
                title="Latest price snapshot is stale",
                message="The latest persisted price snapshot is stale.",
            )
        ],
        latest_checked_at=NOW,
    )

    assert summary.status == "warning"
    assert summary.alert_count == 1
    assert summary.highest_severity == "warning"
    assert summary.critical_alert_count == 0
    assert summary.warning_alert_count == 1


def test_ingestion_health_summary_is_critical_for_critical_alerts():
    """Any critical alert should summarize to critical."""
    summary = summarize_ingestion_health(
        alerts=[
            IngestionHealthAlert(
                alert_type="stale_price_snapshot",
                severity="warning",
                title="Latest price snapshot is stale",
                message="The latest persisted price snapshot is stale.",
            ),
            IngestionHealthAlert(
                alert_type="source_recent_failure",
                severity="critical",
                title="Recent source health failure",
                message="A recent source health check failed.",
            ),
        ],
        latest_checked_at=NOW,
    )

    assert summary.status == "critical"
    assert summary.alert_count == 2
    assert summary.highest_severity == "critical"
    assert summary.critical_alert_count == 1
    assert summary.warning_alert_count == 1


def _alert_types(alerts) -> set[str]:
    return {alert.alert_type for alert in alerts}


def _only_alert_of_type(alerts, alert_type: str):
    matches = [alert for alert in alerts if alert.alert_type == alert_type]
    assert len(matches) == 1
    return matches[0]
