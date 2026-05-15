from collections.abc import Callable
from datetime import UTC
from typing import Any

from apscheduler.schedulers.base import BaseScheduler
from apscheduler.triggers.cron import CronTrigger


HOURLY_MARKET_DATA_INGESTION_JOB_ID = "hourly_market_data_ingestion"


def register_hourly_market_data_ingestion_job(
    scheduler: BaseScheduler,
    ingestion_callable: Callable[[], Any],
) -> None:
    """Register the hourly market data ingestion job without starting a scheduler."""
    scheduler.add_job(
        ingestion_callable,
        trigger=CronTrigger(minute=17, timezone=UTC),
        id=HOURLY_MARKET_DATA_INGESTION_JOB_ID,
        replace_existing=True,
    )
