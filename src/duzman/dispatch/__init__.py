# src/duzman/dispatch/__init__.py
# Dispatch package. Exports the pure domain contract shared by future
# dispatch implementations without binding runtime infrastructure.
"""Pure dispatch contract package."""

from duzman.dispatch.contract import (
    Dispatcher,
    DispatchEvent,
    DispatchResult,
    build_dispatch_event,
)

__all__ = [
    "DispatchEvent",
    "Dispatcher",
    "DispatchResult",
    "build_dispatch_event",
]
