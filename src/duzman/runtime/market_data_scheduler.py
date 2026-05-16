"""Runtime builder for scheduled market data and indicator jobs."""

import asyncio
from collections.abc import Callable
from datetime import UTC

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.orm import Session

from duzman.collectors import BinanceCollector, BybitCollector
from duzman.logging_config import configure_logging
from duzman.repositories import IndicatorRepository
from duzman.scheduler.indicator_jobs import (
    collect_indicators_job,
    register_hourly_indicator_collection_job,
)
from duzman.scheduler.market_data_jobs import register_hourly_market_data_ingestion_job
from duzman.services import PublicMarketDataFetcher, run_public_market_data_ingestion_job


SessionFactory = Callable[[], Session]
FetcherFactory = Callable[[], PublicMarketDataFetcher]
BinanceCollectorFactory = Callable[[], BinanceCollector]
BybitCollectorFactory = Callable[[], BybitCollector]
IndicatorRepositoryFactory = Callable[[], IndicatorRepository]
DAILY_ETF_FLOWS_JOB_ID = "etf_flows_daily"


def build_market_data_scheduler(
    session_factory: SessionFactory | None = None,
    fetcher_factory: FetcherFactory | None = None,
    binance_collector_factory: BinanceCollectorFactory | None = None,
    bybit_collector_factory: BybitCollectorFactory | None = None,
    indicator_repository_factory: IndicatorRepositoryFactory | None = None,
    scheduler: BaseScheduler | None = None,
) -> BaseScheduler:
    """Build a scheduler with the hourly market data job registered but not started."""
    if session_factory is None:
        from duzman.db.session import get_session_factory

        resolved_session_factory = get_session_factory()
    else:
        resolved_session_factory = session_factory
    resolved_fetcher_factory = fetcher_factory or PublicMarketDataFetcher
    resolved_binance_collector_factory = binance_collector_factory or BinanceCollector
    resolved_bybit_collector_factory = bybit_collector_factory or BybitCollector
    resolved_indicator_repository_factory = (
        indicator_repository_factory or IndicatorRepository
    )
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

    def run_indicator_cycle():
        return asyncio.run(
            collect_indicators_job(
                session_factory=resolved_session_factory,
                binance_collector=resolved_binance_collector_factory(),
                bybit_collector=resolved_bybit_collector_factory(),
                repository=resolved_indicator_repository_factory(),
            )
        )

    register_hourly_indicator_collection_job(
        resolved_scheduler,
        run_indicator_cycle,
    )

    def run_etf_flow_cycle():
        from duzman.runtime.farside_jobs import collect_etf_flows_once

        return asyncio.run(
            collect_etf_flows_once(session_factory=resolved_session_factory)
        )

    resolved_scheduler.add_job(
        run_etf_flow_cycle,
        trigger=CronTrigger(hour=2, minute=17, second=0, timezone=UTC),
        id=DAILY_ETF_FLOWS_JOB_ID,
        replace_existing=True,
    )
    return resolved_scheduler


def run_market_data_scheduler_forever(
    session_factory: SessionFactory | None = None,
    fetcher_factory: FetcherFactory | None = None,
    configure_runtime_logging: bool = True,
) -> None:
    """Start the blocking market data scheduler when explicitly invoked."""
    if configure_runtime_logging:
        configure_logging()
    scheduler = BlockingScheduler(timezone=UTC)
    build_market_data_scheduler(
        session_factory=session_factory,
        fetcher_factory=fetcher_factory,
        scheduler=scheduler,
    )
    scheduler.start()


if __name__ == "__main__":
    run_market_data_scheduler_forever()
