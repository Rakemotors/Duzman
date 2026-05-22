# src/duzman/health/server.py
# Uvicorn wrapper for the local health FastAPI application.
# Exports safe bind defaults and the server runner.
"""Uvicorn wrapper for the health service."""

from __future__ import annotations

import os

import uvicorn

from duzman.health.app import get_package_version
from duzman.logging_config import configure_logging, get_logger, log_event

DEFAULT_HEALTH_HOST = "127.0.0.1"
DEFAULT_HEALTH_PORT = 8080


def run_health_server() -> None:
    """Run the local health service with env-configurable bind settings."""
    host = os.environ.get("DUZMAN_HEALTH_HOST", DEFAULT_HEALTH_HOST)
    port = int(os.environ.get("DUZMAN_HEALTH_PORT", str(DEFAULT_HEALTH_PORT)))

    configure_logging()
    log_event(
        get_logger(__name__),
        "health_server_started",
        host=host,
        port=port,
        version=get_package_version(),
    )
    uvicorn.run("duzman.health.app:app", host=host, port=port)
