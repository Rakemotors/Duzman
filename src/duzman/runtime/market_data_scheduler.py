from collections.abc import Callable
from datetime import UTC

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from duzman.scheduler.market_data_jobs import register_hourly_market_data_ingestion_job
from duzman.services import PublicMarketDataFetcher, run_public_market_data_ingestion_job


SessionFactory = Callable[[], Session]
FetcherFactory = Callable[[], PublicMarketDataFetcher]


def build_market_data_scheduler(
    session_factory: SessionFactory | None = None,
    fetcher_factory: FetcherFactory | None = None,
    scheduler: BaseScheduler | None = None,
) -> BaseScheduler:
    """Build a scheduler with the hourly market data job registered but not started."""
    if session_factory is None:
        from duzman.db.session import get_session_factory

        resolved_session_factory = get_session_factory()
    else:
        resolved_session_factory = session_factory
    resolved_fetcher_factory = fetcher_factory or PublicMarketDataFetcher
    resolved_scheduler = scheduler or BackgroundScheduler(timezone=UTC)

    def run_collection_cycle():
        session = resolved_session_factory()
        try:
            return run_public_market_data_ingestion_job(
                session=session,
                fetcher=resolved_fetcher_factory(),
            )
        finally:
            session.close()

    register_hourly_market_data_ingestion_job(
        resolved_scheduler,
        run_collection_cycle,
    )
    return resolved_scheduler


def run_market_data_scheduler_forever(
    session_factory: SessionFactory | None = None,
    fetcher_factory: FetcherFactory | None = None,
) -> None:
    """Start the blocking market data scheduler when explicitly invoked."""
    scheduler = BlockingScheduler(timezone=UTC)
    build_market_data_scheduler(
        session_factory=session_factory,
        fetcher_factory=fetcher_factory,
        scheduler=scheduler,
    )
    scheduler.start()


if __name__ == "__main__":
    run_market_data_scheduler_forever()
