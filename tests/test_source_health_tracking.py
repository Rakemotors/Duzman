from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from duzman.db.models import SourceHealthCheck
from duzman.repositories import SOURCE_HEALTH_FAILED, SOURCE_HEALTH_OK
from duzman.services import SourceHealthTrackingService


def _sqlite_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    SourceHealthCheck.__table__.create(engine)
    return Session(engine)


def test_source_health_tracking_records_ok_on_success():
    """Successful fetch callables should record ok health."""
    session = _sqlite_session()
    service = SourceHealthTrackingService(session)

    result = service.track_fetch("binance", lambda: "payload")
    health_check = session.query(SourceHealthCheck).one()

    assert result.ok is True
    assert result.value == "payload"
    assert health_check.status == SOURCE_HEALTH_OK
    assert health_check.source == "binance"


def test_source_health_tracking_records_failed_on_failure():
    """Failed fetch callables should record failed health and explicit result."""
    session = _sqlite_session()
    service = SourceHealthTrackingService(session)

    def fail_fetch():
        raise RuntimeError("public source unavailable")

    result = service.track_fetch("coingecko", fail_fetch)
    health_check = session.query(SourceHealthCheck).one()

    assert result.ok is False
    assert result.error_message == "public source unavailable"
    assert health_check.status == SOURCE_HEALTH_FAILED
    assert health_check.source == "coingecko"
    assert health_check.error_message == "public source unavailable"

