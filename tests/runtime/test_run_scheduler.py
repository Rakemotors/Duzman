import importlib
import sys
from unittest.mock import Mock


def test_run_scheduler_registers_expected_jobs(monkeypatch) -> None:
    """The runtime entrypoint should use the existing scheduler job set."""
    import duzman.db.session as db_session
    from duzman.runtime.run_scheduler import build_scheduler

    scheduler = Mock()
    session_factory = Mock()
    monkeypatch.setattr(
        db_session,
        "get_session_factory",
        Mock(return_value=session_factory),
    )

    assert build_scheduler(scheduler=scheduler) is scheduler
    assert scheduler.add_job.call_count == 6


def test_import_has_no_side_effects(monkeypatch) -> None:
    """Importing the runtime entrypoint should not initialize scheduler I/O."""
    import apscheduler.schedulers.blocking as blocking_module

    import duzman.runtime.market_data_scheduler as market_data_scheduler

    scheduler_builder = Mock()
    blocking_scheduler = Mock()
    monkeypatch.setattr(
        market_data_scheduler,
        "build_market_data_scheduler",
        scheduler_builder,
    )
    monkeypatch.setattr(blocking_module, "BlockingScheduler", blocking_scheduler)
    sys.modules.pop("duzman.runtime.run_scheduler", None)

    importlib.import_module("duzman.runtime.run_scheduler")

    scheduler_builder.assert_not_called()
    blocking_scheduler.assert_not_called()
