# src/duzman/health/app.py
# Local liveness service for the health runtime entrypoint.
# Exports the FastAPI app and package version resolver.
"""Local-only liveness health service."""

from __future__ import annotations

from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version

from fastapi import FastAPI

import duzman

app = FastAPI(title="Duzman health", version=getattr(duzman, "__version__", "unknown"))


def get_package_version() -> str:
    """Return the Duzman package version without failing health checks."""
    module_version = getattr(duzman, "__version__", None)
    if isinstance(module_version, str) and module_version:
        return module_version
    try:
        return version("duzman")
    except PackageNotFoundError:
        return "unknown"


@app.get("/health")
def read_health() -> dict[str, str]:
    """Return process liveness metadata for local health checks."""
    return {
        "status": "ok",
        "version": get_package_version(),
        "ts": datetime.now(UTC).isoformat(),
    }
