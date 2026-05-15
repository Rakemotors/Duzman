from apscheduler.schedulers.background import BackgroundScheduler

from duzman.scheduler.market_data_jobs import (
    HOURLY_MARKET_DATA_INGESTION_JOB_ID,
    register_hourly_market_data_ingestion_job,
)


def test_register_hourly_market_data_ingestion_job_does_not_start_scheduler():
    """Registering the job should not start a scheduler daemon."""
    scheduler = BackgroundScheduler()

    register_hourly_market_data_ingestion_job(scheduler, lambda: None)
    jobs = scheduler.get_jobs()

    assert scheduler.running is False
    assert len(jobs) == 1
    assert jobs[0].id == HOURLY_MARKET_DATA_INGESTION_JOB_ID
    assert "minute='17'" in str(jobs[0].trigger)

