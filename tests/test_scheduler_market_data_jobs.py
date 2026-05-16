from apscheduler.schedulers.background import BackgroundScheduler

from duzman.scheduler.indicator_jobs import (
    HOURLY_INDICATOR_COLLECTION_JOB_ID,
    register_hourly_indicator_collection_job,
)
from duzman.scheduler.market_data_jobs import (
    HOURLY_MARKET_DATA_INGESTION_JOB_ID,
    register_hourly_market_data_ingestion_job,
)
from duzman.services import run_public_market_data_ingestion_job


def test_register_hourly_market_data_ingestion_job_does_not_start_scheduler():
    """Registering the job should not start a scheduler daemon."""
    scheduler = BackgroundScheduler()

    register_hourly_market_data_ingestion_job(scheduler, lambda: None)
    jobs = scheduler.get_jobs()

    assert scheduler.running is False
    assert len(jobs) == 1
    assert jobs[0].id == HOURLY_MARKET_DATA_INGESTION_JOB_ID
    assert "minute='17'" in str(jobs[0].trigger)


def test_register_hourly_market_data_ingestion_job_accepts_explicit_job_wrapper():
    """Scheduler registration should accept an explicit collection job wrapper."""
    scheduler = BackgroundScheduler()

    register_hourly_market_data_ingestion_job(
        scheduler,
        lambda: run_public_market_data_ingestion_job(session=None),
    )
    job = scheduler.get_jobs()[0]

    assert scheduler.running is False
    assert job.id == HOURLY_MARKET_DATA_INGESTION_JOB_ID


def test_register_hourly_indicator_collection_job_uses_separate_hourly_slot():
    """Indicator collection should run at XX:23 UTC without starting a scheduler."""
    scheduler = BackgroundScheduler()

    register_hourly_indicator_collection_job(scheduler, lambda: None)
    job = scheduler.get_jobs()[0]

    assert scheduler.running is False
    assert job.id == HOURLY_INDICATOR_COLLECTION_JOB_ID
    assert "minute='23'" in str(job.trigger)
