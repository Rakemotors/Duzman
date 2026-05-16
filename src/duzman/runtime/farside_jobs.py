"""Manual runtime entrypoint for collecting public Farside ETF flows."""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from duzman.collectors.farside import FarsideCollector
from duzman.db.models import Asset
from duzman.db.repositories import ETFFlowRepository
from duzman.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    safe_error_message,
)
from duzman.repositories import SourceHealthRepository


SessionFactory = Callable[[], Session]

LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


class _FarsideHealthRecorder:
    """Adapt Farside health calls to the existing source health repository."""

    def __init__(self, repository: SourceHealthRepository) -> None:
        self.repository = repository

    def mark_success(self, source: str) -> None:
        """Record a successful Farside source check."""
        self.repository.record_success(source=source, latency_ms=0)

    def mark_failure(self, source: str, error: str) -> None:
        """Record a failed Farside source check."""
        self.repository.record_failure(source=source, error_message=error)


CollectorFactory = Callable[[_FarsideHealthRecorder], FarsideCollector]


async def collect_etf_flows_once(
    session_factory: SessionFactory | None = None,
    collector_factory: CollectorFactory | None = None,
) -> int:
    """Collect one BTC/ETH ETF flow batch and upsert records into the database."""
    if session_factory is None:
        from duzman.db.session import get_session_factory

        resolved_session_factory = get_session_factory()
    else:
        resolved_session_factory = session_factory

    session = resolved_session_factory()
    logger = get_logger(__name__)
    log_event(logger, "farside_etf_flow_collection_started")
    try:
        repository = ETFFlowRepository(session)
        health_recorder = _FarsideHealthRecorder(SourceHealthRepository(session))
        collector = (
            collector_factory(health_recorder)
            if collector_factory is not None
            else FarsideCollector(health_recorder=health_recorder)
        )
        enabled_assets = _enabled_etf_assets(session)
        records = await collector.fetch_etf_flows(enabled_assets)
        inserted_count = repository.upsert_many(records)
        session.commit()
    except Exception as exc:
        session.rollback()
        log_event(
            logger,
            "farside_etf_flow_collection_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        raise
    finally:
        session.close()

    log_event(
        logger,
        "farside_etf_flow_collection_completed",
        asset_count=len(enabled_assets),
        record_count=len(records),
        inserted_count=inserted_count,
    )
    return inserted_count


def main(argv: Sequence[str] | None = None) -> int:
    """Run one public Farside ETF flow collection cycle from the command line."""
    args = _build_parser().parse_args(list(argv or ()))
    configure_logging(level=LOG_LEVELS[args.log_level])
    try:
        import asyncio

        asyncio.run(collect_etf_flows_once())
    except Exception as exc:
        log_event(
            get_logger(__name__),
            "farside_etf_flow_command_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        return 1
    return 0


def _enabled_etf_assets(session: Session) -> list[str]:
    statement = (
        select(Asset.symbol)
        .where(Asset.enabled.is_(True), Asset.symbol.in_(("BTC", "ETH")))
        .order_by(Asset.symbol)
    )
    return list(session.scalars(statement))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect one public Farside ETF flow batch.",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(LOG_LEVELS),
        default="INFO",
        help="Runtime log level for the Farside ETF flow command.",
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
