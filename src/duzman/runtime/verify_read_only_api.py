"""Offline smoke check for Duzman read-only FastAPI route registration."""

from __future__ import annotations

from collections.abc import Sequence

from duzman.api import create_app


EXPECTED_MARKET_DATA_ROUTES: frozenset[str] = frozenset(
    {
        "/api/market-data/prices/latest",
        "/api/market-data/source-health",
        "/api/market-data/ingestion-status",
    }
)


def verify_read_only_api_app() -> tuple[str, ...]:
    """Create the FastAPI app and return the registered market data routes."""
    app = create_app()
    registered_paths = {route.path for route in app.routes}
    missing_paths = EXPECTED_MARKET_DATA_ROUTES - registered_paths
    if missing_paths:
        missing = ", ".join(sorted(missing_paths))
        raise RuntimeError(f"Missing read-only API routes: {missing}")
    return tuple(sorted(EXPECTED_MARKET_DATA_ROUTES))


def main(argv: Sequence[str] | None = None) -> int:
    """Run the offline read-only API smoke check and return a process exit code."""
    verify_read_only_api_app()
    print("READ_ONLY_API_RUNTIME_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
