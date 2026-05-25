"""Runtime builder for scheduled market data and indicator jobs."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import-untyped]
from apscheduler.schedulers.base import BaseScheduler  # type: ignore[import-untyped]
from apscheduler.schedulers.blocking import BlockingScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from duzman.collectors import BinanceCollector, BybitCollector
from duzman.db.models import PatternTrigger
from duzman.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    safe_error_message,
)
from duzman.patterns.evaluation import PatternMatch
from duzman.repositories import IndicatorRepository
from duzman.scheduler.hourly_tick import (
    SessionFactory as PatternSessionFactory,
)
from duzman.scheduler.hourly_tick import (
    SnapshotBuilder,
    run_hourly_pattern_tick,
)
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
DAILY_FEAR_GREED_JOB_ID = "fear_greed_daily"
HOURLY_COINGLASS_JOB_ID = "coinglass_hourly"
HOURLY_COINGECKO_GLOBAL_JOB_ID = "coingecko_global_hourly"
HOURLY_PATTERN_TICK_JOB_ID = "pattern_tick_hourly"
LOGGER = get_logger(__name__)


def build_market_data_scheduler(
    session_factory: SessionFactory | None = None,
    pattern_session_factory: PatternSessionFactory | None = None,
    pattern_snapshot_builder: SnapshotBuilder | None = None,
    fetcher_factory: FetcherFactory | None = None,
    binance_collector_factory: BinanceCollectorFactory | None = None,
    bybit_collector_factory: BybitCollectorFactory | None = None,
    indicator_repository_factory: IndicatorRepositoryFactory | None = None,
    scheduler: BaseScheduler | None = None,
) -> BaseScheduler:
    """Build a scheduler with the hourly market data job registered but not started."""
    resolved_session_factory: SessionFactory
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
    lazy_pattern_session_factory = _LazyPatternSessionFactory(pattern_session_factory)

    def run_collection_cycle() -> object:
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

    def run_indicator_cycle() -> object:
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

    def run_pattern_tick_cycle() -> list[PatternMatch]:
        return _run_observation_only_pattern_tick_cycle(
            session_factory=lazy_pattern_session_factory,
            snapshot_builder=pattern_snapshot_builder,
        )

    resolved_scheduler.add_job(
        run_pattern_tick_cycle,
        trigger=CronTrigger(minute=33, second=0, timezone=UTC),
        id=HOURLY_PATTERN_TICK_JOB_ID,
        replace_existing=True,
    )

    def run_etf_flow_cycle() -> object:
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

    def run_fear_greed_cycle() -> object:
        from duzman.runtime.alternative_me_jobs import collect_fear_greed_once

        return asyncio.run(
            collect_fear_greed_once(session_factory=resolved_session_factory)
        )

    resolved_scheduler.add_job(
        run_fear_greed_cycle,
        trigger=CronTrigger(hour=2, minute=17, second=0, timezone=UTC),
        id=DAILY_FEAR_GREED_JOB_ID,
        replace_existing=True,
    )

    def run_coinglass_cycle() -> object:
        from duzman.runtime.coinglass_jobs import (
            collect_heatmaps_once,
            collect_liquidations_once,
        )

        async def run_sequentially() -> None:
            await collect_liquidations_once(session_factory=resolved_session_factory)
            await collect_heatmaps_once(session_factory=resolved_session_factory)

        return asyncio.run(run_sequentially())

    resolved_scheduler.add_job(
        run_coinglass_cycle,
        trigger=CronTrigger(minute=18, second=0, timezone=UTC),
        id=HOURLY_COINGLASS_JOB_ID,
        replace_existing=True,
    )

    def run_coingecko_global_cycle() -> object:
        from duzman.runtime.coingecko_global_jobs import collect_btc_dominance_once

        return asyncio.run(
            collect_btc_dominance_once(session_factory=resolved_session_factory)
        )

    resolved_scheduler.add_job(
        run_coingecko_global_cycle,
        trigger=CronTrigger(minute=17, second=0, timezone=UTC),
        id=HOURLY_COINGECKO_GLOBAL_JOB_ID,
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


class _LazyPatternSessionFactory:
    """Lazily build the async DB session factory used by the pattern tick."""

    def __init__(self, injected_factory: PatternSessionFactory | None = None) -> None:
        self._injected_factory = injected_factory
        self._runtime_factory: PatternSessionFactory | None = None

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        """Return a new async session context manager."""
        return self._resolve_factory()()

    def _resolve_factory(self) -> PatternSessionFactory:
        """Return the injected or runtime-built pattern session factory."""
        if self._injected_factory is not None:
            return self._injected_factory
        if self._runtime_factory is None:
            from duzman.db.session_async import build_async_database_session_components
            from duzman.settings import settings

            self._runtime_factory = build_async_database_session_components(
                settings
            ).session_factory
        return self._runtime_factory


def _run_observation_only_pattern_tick_cycle(
    session_factory: PatternSessionFactory,
    snapshot_builder: SnapshotBuilder | None = None,
) -> list[PatternMatch]:
    """Run one observation-only pattern tick and log cycle-level counts."""
    started_ns = time.monotonic_ns()
    tick_ts = datetime.now(UTC)
    try:
        if snapshot_builder is None:
            allowed_matches = asyncio.run(
                run_hourly_pattern_tick(
                    session_factory=session_factory,
                    tick_ts=tick_ts,
                )
            )
        else:
            allowed_matches = asyncio.run(
                run_hourly_pattern_tick(
                    session_factory=session_factory,
                    tick_ts=tick_ts,
                    snapshot_builder=snapshot_builder,
                )
            )
        total_matches = asyncio.run(
            _count_pattern_triggers_at_tick(session_factory, tick_ts)
        )
    except Exception as exc:
        log_event(
            LOGGER,
            "pattern_tick_cycle_failed",
            level=logging.ERROR,
            safe_error_message=safe_error_message(exc),
            elapsed_ms=_elapsed_ms_since(started_ns),
        )
        raise

    log_event(
        LOGGER,
        "pattern_tick_cycle_completed",
        allowed_count=len(allowed_matches),
        total_matches=total_matches,
        elapsed_ms=_elapsed_ms_since(started_ns),
    )
    return allowed_matches


async def _count_pattern_triggers_at_tick(
    session_factory: PatternSessionFactory,
    tick_ts: datetime,
) -> int:
    """Count persisted pattern trigger decisions for one tick timestamp."""
    async with session_factory() as session:
        return await _count_pattern_trigger_rows(session, tick_ts)


async def _count_pattern_trigger_rows(session: AsyncSession, tick_ts: datetime) -> int:
    """Count pattern trigger rows persisted with the shared tick timestamp."""
    count = await session.scalar(
        select(func.count()).select_from(PatternTrigger).where(PatternTrigger.ts == tick_ts)
    )
    return int(count or 0)


def _elapsed_ms_since(started_ns: int) -> int:
    """Return elapsed monotonic time in milliseconds."""
    return (time.monotonic_ns() - started_ns) // 1_000_000


if __name__ == "__main__":
    run_market_data_scheduler_forever()
