"""Safe structured logging helpers for Duzman runtime code."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"
DEFAULT_MAX_ERROR_MESSAGE_LENGTH = 500
SENSITIVE_FIELD_PATTERN = re.compile(
    r"\b(api[_-]?key|access[_-]?token|token|password|secret|seed[_-]?phrase|private[_-]?key|database[_-]?url)"
    r"\s*=\s*[^\s&]+",
    flags=re.IGNORECASE,
)


def configure_logging(level: int = logging.INFO) -> None:
    """Configure standard-library logging when a runtime entrypoint is invoked."""
    logging.basicConfig(level=level, format=DEFAULT_LOG_FORMAT)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named application logger without configuring global logging."""
    return logging.getLogger(name)


def safe_error_message(
    error: BaseException | str,
    max_length: int = DEFAULT_MAX_ERROR_MESSAGE_LENGTH,
) -> str:
    """Return a bounded one-line error message suitable for logs and health checks."""
    message = str(error).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    message = SENSITIVE_FIELD_PATTERN.sub(_redacted_sensitive_field, message)
    if max_length <= 0:
        return ""
    if len(message) <= max_length:
        return message
    if max_length <= 3:
        return message[:max_length]
    return f"{message[: max_length - 3]}..."


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured key=value event while avoiding raw mapping payloads."""
    if fields:
        logger.log(level, "%s %s", event, _format_fields(fields))
    else:
        logger.log(level, "%s", event)


def _format_fields(fields: Mapping[str, Any]) -> str:
    return " ".join(
        f"{name}={_format_value(value)}"
        for name, value in fields.items()
        if value is not None
    )


def _format_value(value: Any) -> str:
    if isinstance(value, Mapping):
        return "<mapping>"
    if isinstance(value, (list, tuple, set, frozenset)):
        return ",".join(str(item) for item in value)
    return str(value).replace("\n", " ").replace("\r", " ").replace("\t", " ")


def _redacted_sensitive_field(match: re.Match[str]) -> str:
    return f"{match.group(1)}=<redacted>"
