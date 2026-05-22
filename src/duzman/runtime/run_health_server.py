# src/duzman/runtime/run_health_server.py
# Manual entrypoint for the loopback-bound health liveness service.
# Exports main for `python -m duzman.runtime.run_health_server`.
"""Manual entrypoint to run the local health service."""

from __future__ import annotations

from duzman.health.server import run_health_server


def main() -> None:
    """Run the local health server until uvicorn stops."""
    run_health_server()


if __name__ == "__main__":
    main()
