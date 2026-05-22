# src/duzman/runtime/run_scheduler.py
# Long-running entrypoint for the existing runtime scheduler assembly.
# Exports the scheduler builder wrapper and command-line main function.
"""Long-running scheduler runtime entrypoint."""

from __future__ import annotations

import logging
from datetime import UTC

from apscheduler.schedulers.base import BaseScheduler  # type: ignore[import-untyped]
from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore[import-untyped]

from duzman.health.app import get_package_version
from duzman.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    safe_error_message,
)
from duzman.runtime.market_data_scheduler import build_market_data_scheduler


def build_scheduler(scheduler: BaseScheduler | None = None) -> BaseScheduler:
    """Build the long-running scheduler without starting it."""
    resolved_scheduler = scheduler or BlockingScheduler(timezone=UTC)
    return build_market_data_scheduler(scheduler=resolved_scheduler)


def main() -> int:
    """Run the runtime scheduler until the process is stopped."""
    configure_logging()
    logger = get_logger(__name__)
    try:
        scheduler = build_scheduler()
        log_event(
            logger,
            "scheduler_started",
            jobs_count=len(scheduler.get_jobs()),
            version=get_package_version(),
        )
        scheduler.start()
    except Exception as exc:
        log_event(
            logger,
            "scheduler_startup_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
