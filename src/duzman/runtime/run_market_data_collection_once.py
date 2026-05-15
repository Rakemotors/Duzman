"""One-shot runtime command for a single public market data collection cycle."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import logging
import sys

from sqlalchemy.orm import Session

from duzman.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    safe_error_message,
)
from duzman.services import (
    MarketDataCollectionResult,
    PublicMarketDataFetcher,
    run_public_market_data_ingestion_job,
)


SessionFactory = Callable[[], Session]
FetcherFactory = Callable[[], PublicMarketDataFetcher]
CollectionRunner = Callable[[], MarketDataCollectionResult]

LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def run_one_market_data_collection_cycle(
    session_factory: SessionFactory | None = None,
    fetcher_factory: FetcherFactory | None = None,
) -> MarketDataCollectionResult:
    """Run one public market-data collection cycle with runtime dependencies."""
    if session_factory is None:
        from duzman.db.session import get_session_factory

        resolved_session_factory = get_session_factory()
    else:
        resolved_session_factory = session_factory
    resolved_fetcher_factory = fetcher_factory or PublicMarketDataFetcher

    session = resolved_session_factory()
    try:
        return run_public_market_data_ingestion_job(
            session=session,
            fetcher=resolved_fetcher_factory(),
        )
    finally:
        session.close()


def main(
    argv: Sequence[str] | None = None,
    session_factory: SessionFactory | None = None,
    fetcher_factory: FetcherFactory | None = None,
    collection_runner: CollectionRunner | None = None,
) -> int:
    """Run exactly one public market-data collection cycle and return an exit code."""
    args = _build_parser().parse_args(list(argv or ()))
    configure_logging(level=LOG_LEVELS[args.log_level])
    logger = get_logger(__name__)
    log_event(logger, "one_shot_collection_command_started", log_level=args.log_level)

    try:
        if collection_runner is None:
            result = run_one_market_data_collection_cycle(
                session_factory=session_factory,
                fetcher_factory=fetcher_factory,
            )
        else:
            result = collection_runner()
    except Exception as exc:
        log_event(
            logger,
            "one_shot_collection_command_failed",
            level=logging.ERROR,
            error_type=type(exc).__name__,
            safe_error_message=safe_error_message(exc),
        )
        return 1

    if result.failed_sources:
        log_event(
            logger,
            "one_shot_collection_command_failed",
            level=logging.ERROR,
            attempted_sources=result.attempted_sources,
            successful_sources=result.successful_sources,
            failed_sources=result.failed_sources,
            snapshots_created=result.snapshots_created,
            health_checks_created=result.health_checks_created,
            safe_error_message=safe_error_message(_format_collection_errors(result)),
        )
        return 1

    log_event(
        logger,
        "one_shot_collection_command_succeeded",
        attempted_sources=result.attempted_sources,
        successful_sources=result.successful_sources,
        snapshots_created=result.snapshots_created,
        health_checks_created=result.health_checks_created,
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one Duzman public market-data collection cycle.",
    )
    parser.add_argument(
        "--log-level",
        choices=tuple(LOG_LEVELS),
        default="INFO",
        help="Runtime log level for the one-shot command.",
    )
    return parser


def _format_collection_errors(result: MarketDataCollectionResult) -> str:
    return "; ".join(
        f"{source}={message}" for source, message in result.errors.items()
    ) or "one or more public sources failed"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
