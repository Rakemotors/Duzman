"""Manual runtime job for Alternative.me Fear & Greed Index."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

from duzman.collectors.alternative_me import AlternativeMeCollector
from duzman.db.repositories import GlobalMetricRepository
from duzman.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    safe_error_message,
)
from duzman.repositories import SourceHealthRepository


SessionFactory = Callable[[], Session]
CollectorFactory = Callable[["_AlternativeMeHealthRecorder"], AlternativeMeCollector]

LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


class _AlternativeMeHealthRecorder:
    """Adapt Alternative.me health calls to the existing repository."""

    def __init__(self, repository: SourceHealthRepository) -> None:
        self.repository = repository

    def mark_success(self, source: str) -> None:
        """Record a successful Alternative.me source check."""
        self.repository.record_success(source=source, latency_ms=0)

    def mark_failure(self, source: str, error: str) -> None:
        """Record a failed Alternative.me source check."""
        self.repository.record_failure(source=source, error_message=error)


async def collect_fear_greed_once(
    session_factory: SessionFactory | None = None,
    collector_factory: CollectorFactory | None = None,
) -> int:
    """Collect one Fear & Greed Index value and persist it as a global metric."""
    session = _open_session(session_factory)
    logger = get_logger(__name__)
    log_event(logger, "alternative_me_collection_started")
    try:
        repository = GlobalMetricRepository(session)
        health_recorder = _AlternativeMeHealthRecorder(SourceHealthRepository(session))
        collector = (
            collector_factory(health_recorder)
            if collector_factory is not None
            else AlternativeMeCollector(health_recorder=health_recorder)
        )
        record = await collector.fetch_fear_greed()
        inserted_count = 0
        if record is not None:
            repository.insert_one(record)
            inserted_count = 1
        session.commit()
    except Exception as exc:
        session.rollback()
        log_event(
            logger,
            "alternative_me_collection_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        raise
    finally:
        session.close()

    log_event(
        logger,
        "alternative_me_collection_completed",
        inserted_count=inserted_count,
    )
    return inserted_count


def main(argv: Sequence[str] | None = None) -> int:
    """Run one Alternative.me Fear & Greed collection cycle."""
    args = _build_parser().parse_args(list(argv or ()))
    configure_logging(level=LOG_LEVELS[args.log_level])
    try:
        import asyncio

        asyncio.run(collect_fear_greed_once())
    except Exception as exc:
        log_event(
            get_logger(__name__),
            "alternative_me_command_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        return 1
    return 0


def _open_session(session_factory: SessionFactory | None) -> Session:
    if session_factory is None:
        from duzman.db.session import get_session_factory

        return get_session_factory()()
    return session_factory()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect one public Alternative.me Fear & Greed metric.",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(LOG_LEVELS),
        default="INFO",
        help="Runtime log level for the Alternative.me command.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
