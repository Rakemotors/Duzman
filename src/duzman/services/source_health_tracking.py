from collections.abc import Callable
from dataclasses import dataclass
import logging
from time import monotonic
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from duzman.logging_config import get_logger, log_event, safe_error_message
from duzman.repositories import SourceHealthRepository


T = TypeVar("T")


@dataclass(frozen=True)
class SourceHealthTrackingResult(Generic[T]):
    """Explicit result for a public source fetch wrapped with health tracking."""

    ok: bool
    value: T | None = None
    error_message: str | None = None
    error_type: str | None = None


class SourceHealthTrackingService:
    """Record source health around explicit public fetch attempts."""

    def __init__(
        self,
        session: Session,
        repository: SourceHealthRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or SourceHealthRepository(session)
        self.logger = get_logger(__name__)

    def track_fetch(
        self,
        source: str,
        fetch_callable: Callable[[], T],
    ) -> SourceHealthTrackingResult[T]:
        """Run one fetch callable and record ok/failed source health."""
        started_at = monotonic()
        try:
            value = fetch_callable()
        except Exception as exc:
            latency_ms = self._elapsed_ms(started_at)
            error_message = safe_error_message(exc)
            error_type = type(exc).__name__
            self.repository.record_failure(
                source=source,
                error_message=error_message,
                latency_ms=latency_ms,
            )
            self.session.commit()
            log_event(
                self.logger,
                "source_health_recorded_failed",
                level=logging.ERROR,
                source=source,
                latency_ms=latency_ms,
                error_type=error_type,
                safe_error_message=error_message,
            )
            return SourceHealthTrackingResult(
                ok=False,
                error_message=error_message,
                error_type=error_type,
            )

        latency_ms = self._elapsed_ms(started_at)
        self.repository.record_success(source=source, latency_ms=latency_ms)
        self.session.commit()
        log_event(
            self.logger,
            "source_health_recorded_ok",
            source=source,
            latency_ms=latency_ms,
        )
        return SourceHealthTrackingResult(ok=True, value=value)

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))
