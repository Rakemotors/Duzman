# src/duzman/runtime/run_ai_explanation_worker.py
# Runtime entrypoint for the optional Day 8 AI explanation worker.
"""Run the AI explanation worker in daemon or one-shot mode."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from collections.abc import Sequence

from duzman.ai.app import build_components_from_settings, dispose_components
from duzman.logging_config import configure_logging, safe_error_message
from duzman.settings import Settings

LOGGER = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the AI explanation worker command and return a process exit code."""
    args = _build_parser().parse_args(list(argv or ()))
    configure_logging()
    return asyncio.run(_async_main(args))


async def _async_main(args: argparse.Namespace) -> int:
    """Run the worker according to parsed CLI arguments."""
    try:
        settings = Settings()
        if not settings.ai_explanations_enabled:
            LOGGER.info("ai explanations disabled, exiting")
            return 0
        if not settings.anthropic_api_key.get_secret_value():
            LOGGER.error("ANTHROPIC_API_KEY missing while AI_EXPLANATIONS_ENABLED=true")
            return 2

        components = build_components_from_settings(settings)
        try:
            if args.run_once:
                processed = await components.worker.run_once()
                LOGGER.info("run_once processed %s task(s)", processed)
                return 0

            stop_event = asyncio.Event()
            _install_signal_handlers(stop_event)
            LOGGER.info("starting ai explanation worker loop")
            await components.worker.run_forever(stop_event=stop_event)
            LOGGER.info("worker stopped")
            return 0
        finally:
            await dispose_components(components)
    except Exception as exc:
        LOGGER.exception(
            "ai explanation worker failed: %s",
            safe_error_message(exc),
        )
        return 1


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the AI explanation worker."""
    parser = argparse.ArgumentParser(
        description="Run the Duzman AI explanation worker.",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process one worker tick and exit.",
    )
    return parser


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Install SIGTERM/SIGINT handlers that request graceful shutdown."""
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except NotImplementedError:  # pragma: no cover - platform specific.
            signal.signal(signum, lambda *_: stop_event.set())


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
