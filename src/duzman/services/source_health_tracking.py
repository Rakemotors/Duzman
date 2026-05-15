from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic
from typing import Generic, TypeVar

from sqlalchemy.orm import Session

from duzman.repositories import SourceHealthRepository


T = TypeVar("T")


@dataclass(frozen=True)
class SourceHealthTrackingResult(Generic[T]):
    """Explicit result for a public source fetch wrapped with health tracking."""

    ok: bool
    value: T | None = None
    error_message: str | None = None


class SourceHealthTrackingService:
    """Record source health around explicit public fetch attempts."""

    def __init__(
        self,
        session: Session,
        repository: SourceHealthRepository | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or SourceHealthRepository(session)

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
            self.repository.record_failure(
                source=source,
                error_message=str(exc),
                latency_ms=latency_ms,
            )
            self.session.commit()
            return SourceHealthTrackingResult(
                ok=False,
                error_message=str(exc),
            )

        latency_ms = self._elapsed_ms(started_at)
        self.repository.record_success(source=source, latency_ms=latency_ms)
        self.session.commit()
        return SourceHealthTrackingResult(ok=True, value=value)

    def _elapsed_ms(self, started_at: float) -> int:
        return max(0, int((monotonic() - started_at) * 1000))

