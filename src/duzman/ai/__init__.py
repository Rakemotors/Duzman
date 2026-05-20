# src/duzman/ai/__init__.py
# AI explanation package. Exports explicit helpers only; imports do not call
# external APIs or read secrets.
"""AI explanation support for AlertGate alerts."""

from duzman.ai.anthropic_client import (
    AnthropicCallError,
    AnthropicClient,
    ExplanationResult,
)

__all__ = ["AnthropicCallError", "AnthropicClient", "ExplanationResult"]
