from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from duzman.db.models import SourceHealthCheck
from duzman.repositories import (
    SOURCE_HEALTH_FAILED,
    SOURCE_HEALTH_OK,
    SourceHealthRepository,
)


def _sqlite_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SourceHealthCheck.__table__.create(engine)
    return Session(engine)


def test_source_health_check_model_has_required_columns():
    """SourceHealthCheck metadata should expose status and timing fields."""
    columns = set(SourceHealthCheck.__table__.columns.keys())

    assert {
        "id",
        "source",
        "status",
        "checked_at",
        "latency_ms",
        "error_message",
        "created_at",
    } <= columns


def test_source_health_repository_records_ok_status():
    """The repository should persist an ok health check."""
    session = _sqlite_session()
    repository = SourceHealthRepository(session)
    checked_at = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)

    health_check = repository.record_success("binance", latency_ms=25, checked_at=checked_at)
    session.commit()

    assert health_check.status == SOURCE_HEALTH_OK
    assert health_check.source == "binance"
    assert health_check.latency_ms == 25
    assert repository.latest_by_source("binance").id == health_check.id


def test_source_health_repository_records_failed_status_with_safe_error():
    """Failure errors should be persisted with bounded message length."""
    session = _sqlite_session()
    repository = SourceHealthRepository(session)

    health_check = repository.record_failure(
        "coingecko",
        error_message="x" * 800,
        latency_ms=100,
    )
    session.commit()

    assert health_check.status == SOURCE_HEALTH_FAILED
    assert health_check.source == "coingecko"
    assert len(health_check.error_message) == 500

