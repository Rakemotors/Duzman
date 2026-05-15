import logging
from datetime import datetime, timezone

from duzman.services import MarketDataCollectionResult


def _collection_result(
    failed_sources: tuple[str, ...] = (),
    errors: dict[str, str] | None = None,
) -> MarketDataCollectionResult:
    now = datetime(2026, 5, 15, 12, 17, tzinfo=timezone.utc)
    return MarketDataCollectionResult(
        started_at=now,
        finished_at=now,
        attempted_sources=("binance", "coingecko"),
        successful_sources=("binance", "coingecko")
        if not failed_sources
        else ("binance",),
        failed_sources=failed_sources,
        snapshots_created=4 if not failed_sources else 2,
        health_checks_created=2,
        errors=errors or {},
    )


def test_one_shot_module_import_has_no_collection_side_effects():
    """Importing the one-shot module should not run collection or scheduling."""
    import duzman.runtime.run_market_data_collection_once as one_shot

    assert callable(one_shot.main)
    assert callable(one_shot.run_one_market_data_collection_cycle)


def test_one_shot_main_returns_zero_and_logs_success(caplog):
    """Successful one-shot collection should return zero and emit safe logs."""
    import duzman.runtime.run_market_data_collection_once as one_shot

    caplog.set_level(logging.INFO)
    exit_code = one_shot.main(
        argv=["--log-level", "INFO"],
        collection_runner=lambda: _collection_result(),
    )

    assert exit_code == 0
    assert "one_shot_collection_command_started log_level=INFO" in caplog.text
    assert "one_shot_collection_command_succeeded" in caplog.text


def test_one_shot_main_returns_nonzero_for_partial_failure(caplog):
    """Controlled source failures should return non-zero without raw secret values."""
    import duzman.runtime.run_market_data_collection_once as one_shot

    caplog.set_level(logging.INFO)
    exit_code = one_shot.main(
        collection_runner=lambda: _collection_result(
            failed_sources=("coingecko",),
            errors={"coingecko": "token=SHOULD_NOT_APPEAR"},
        ),
    )

    assert exit_code == 1
    assert "one_shot_collection_command_failed" in caplog.text
    assert "failed_sources=coingecko" in caplog.text
    assert "SHOULD_NOT_APPEAR" not in caplog.text
    assert "token=<redacted>" in caplog.text


def test_one_shot_main_returns_nonzero_for_unhandled_failure(caplog):
    """Unexpected runtime failures should be converted to a controlled exit code."""
    import duzman.runtime.run_market_data_collection_once as one_shot

    def fail_collection():
        raise RuntimeError("password=SHOULD_NOT_APPEAR")

    caplog.set_level(logging.INFO)
    exit_code = one_shot.main(collection_runner=fail_collection)

    assert exit_code == 1
    assert "one_shot_collection_command_failed" in caplog.text
    assert "error_type=RuntimeError" in caplog.text
    assert "SHOULD_NOT_APPEAR" not in caplog.text


def test_one_shot_main_does_not_start_scheduler(monkeypatch):
    """The one-shot command should not construct or start APScheduler."""
    import duzman.runtime.market_data_scheduler as scheduler_runtime
    import duzman.runtime.run_market_data_collection_once as one_shot

    def fail_if_scheduler_starts(*args, **kwargs):
        raise AssertionError("scheduler runtime should not be used")

    monkeypatch.setattr(
        scheduler_runtime,
        "run_market_data_scheduler_forever",
        fail_if_scheduler_starts,
    )

    exit_code = one_shot.main(collection_runner=lambda: _collection_result())

    assert exit_code == 0
