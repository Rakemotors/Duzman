# src/duzman/dispatch/__init__.py
# Dispatch package. Exports pure dispatch contracts and inert dispatch-facing
# helper layers without binding runtime infrastructure.
"""Pure dispatch contract and helper package."""

from duzman.dispatch.ai_worker import (
    CachedDispatchExplanation,
    DispatchAIExplanationResult,
    DispatchAIExplanationWorker,
    DispatchExplanationCache,
    DispatchExplanationGenerator,
    DispatchExplanationProviderError,
    DispatchExplanationRequest,
    DispatchGeneratedExplanation,
    build_dispatch_explanation_request,
)
from duzman.dispatch.contract import (
    Dispatcher,
    DispatchEvent,
    DispatchResult,
    build_dispatch_event,
)

__all__ = [
    "CachedDispatchExplanation",
    "DispatchAIExplanationResult",
    "DispatchAIExplanationWorker",
    "DispatchEvent",
    "DispatchExplanationCache",
    "DispatchExplanationGenerator",
    "DispatchExplanationProviderError",
    "DispatchExplanationRequest",
    "DispatchGeneratedExplanation",
    "Dispatcher",
    "DispatchResult",
    "build_dispatch_explanation_request",
    "build_dispatch_event",
]
