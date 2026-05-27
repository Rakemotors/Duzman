# src/duzman/health/app.py
# Local liveness service for the health runtime entrypoint.
# Exports the FastAPI app plus package and build metadata resolvers.
"""Local-only liveness health service."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from fastapi import FastAPI

import duzman

app = FastAPI(title="Duzman health", version=getattr(duzman, "__version__", "unknown"))
BUILD_SHA_FILENAME = "BUILD_SHA"
BUILD_SHA_ENV_VAR = "DUZMAN_BUILD_SHA"
BUILD_SHA_PATH_ENV_VAR = "DUZMAN_BUILD_SHA_PATH"


def get_package_version() -> str:
    """Return the Duzman package version without failing health checks."""
    module_version = getattr(duzman, "__version__", None)
    if isinstance(module_version, str) and module_version:
        return module_version
    try:
        return version("duzman")
    except PackageNotFoundError:
        return "unknown"


def get_build_sha() -> str:
    """Return explicit build SHA metadata without failing health checks."""
    build_sha_path = _resolve_build_sha_file_path()
    try:
        file_value = build_sha_path.read_text(encoding="utf-8").strip()
    except OSError:
        file_value = ""
    if file_value:
        return file_value

    env_value = os.environ.get(BUILD_SHA_ENV_VAR, "").strip()
    if env_value:
        return env_value
    return "unknown"


def _resolve_build_sha_file_path() -> Path:
    """Return the configured or package-anchored build SHA file path."""
    override_path = os.environ.get(BUILD_SHA_PATH_ENV_VAR, "").strip()
    if override_path:
        return Path(override_path)
    return Path(duzman.__file__).resolve().parent.parent.parent / BUILD_SHA_FILENAME


@app.get("/health")
def read_health() -> dict[str, str]:
    """Return process liveness metadata for local health checks."""
    return {
        "status": "ok",
        "version": get_package_version(),
        "build_sha": get_build_sha(),
        "ts": datetime.now(UTC).isoformat(),
    }
