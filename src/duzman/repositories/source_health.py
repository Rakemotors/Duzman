from datetime import datetime, timezone

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from duzman.db.models import SourceHealthCheck


SOURCE_HEALTH_OK = "ok"
SOURCE_HEALTH_FAILED = "failed"
SOURCE_HEALTH_DEGRADED = "degraded"
MAX_SOURCE_HEALTH_ERROR_LENGTH = 500


class SourceHealthRepository:
    """Persist and query public source health check results."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def record_success(
        self,
        source: str,
        latency_ms: int,
        checked_at: datetime | None = None,
    ) -> SourceHealthCheck:
        """Record a successful public source check."""
        return self._record_check(
            source=source,
            status=SOURCE_HEALTH_OK,
            latency_ms=latency_ms,
            error_message=None,
            checked_at=checked_at,
        )

    def record_failure(
        self,
        source: str,
        error_message: str,
        latency_ms: int | None = None,
        checked_at: datetime | None = None,
    ) -> SourceHealthCheck:
        """Record a failed public source check with a bounded error message."""
        return self._record_check(
            source=source,
            status=SOURCE_HEALTH_FAILED,
            latency_ms=latency_ms,
            error_message=self._safe_error_message(error_message),
            checked_at=checked_at,
        )

    def latest_by_source(self, source: str) -> SourceHealthCheck | None:
        """Return the latest health check for one source."""
        statement: Select[tuple[SourceHealthCheck]] = (
            select(SourceHealthCheck)
            .where(SourceHealthCheck.source == source)
            .order_by(SourceHealthCheck.checked_at.desc())
            .limit(1)
        )
        return self.session.scalars(statement).first()

    def list_latest(
        self,
        source: str | None = None,
        limit: int = 100,
    ) -> list[SourceHealthCheck]:
        """Return latest source health checks, one record per source when unfiltered."""
        if source is not None:
            latest = self.latest_by_source(source)
            return [latest] if latest is not None else []

        statement: Select[tuple[SourceHealthCheck]] = (
            select(SourceHealthCheck)
            .order_by(SourceHealthCheck.checked_at.desc())
            .limit(limit)
        )
        latest_by_source: dict[str, SourceHealthCheck] = {}
        for health_check in self.session.scalars(statement):
            latest_by_source.setdefault(health_check.source, health_check)
        return list(latest_by_source.values())

    def _record_check(
        self,
        source: str,
        status: str,
        latency_ms: int | None,
        error_message: str | None,
        checked_at: datetime | None,
    ) -> SourceHealthCheck:
        health_check = SourceHealthCheck(
            source=source,
            status=status,
            checked_at=checked_at or datetime.now(timezone.utc),
            latency_ms=latency_ms,
            error_message=error_message,
        )
        self.session.add(health_check)
        self.session.flush()
        self.session.refresh(health_check)
        return health_check

    def _safe_error_message(self, error_message: str) -> str:
        return error_message[:MAX_SOURCE_HEALTH_ERROR_LENGTH]
