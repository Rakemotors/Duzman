import logging

from duzman.logging_config import (
    configure_logging,
    get_logger,
    log_event,
    safe_error_message,
)


def test_logging_helper_can_emit_structured_event(caplog):
    """Logging helpers should emit key=value events only when called."""
    configure_logging()
    logger = get_logger("duzman.tests.logging")

    caplog.set_level(logging.INFO, logger="duzman.tests.logging")
    log_event(logger, "test_event", source="binance", raw_payload={"secret": "value"})

    assert "test_event source=binance raw_payload=<mapping>" in caplog.text
    assert "secret" not in caplog.text
    assert "value" not in caplog.text


def test_safe_error_message_bounds_and_flattens_long_errors():
    """Long multi-line errors should be bounded before they reach logs."""
    message = safe_error_message("line one\n" + ("x" * 80), max_length=32)

    assert len(message) == 32
    assert "\n" not in message
    assert message.endswith("...")


def test_safe_error_message_redacts_secret_like_fields():
    """Secret-looking key/value fragments should not reach logs."""
    message = safe_error_message("request failed token=SHOULD_NOT_APPEAR")

    assert "SHOULD_NOT_APPEAR" not in message
    assert "token=<redacted>" in message
