# src/duzman/ai/anthropic_client.py
# Anthropic Messages API adapter. Keeps API-key handling and response parsing
# isolated from explanation orchestration.
"""Thin async Anthropic Messages API client."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic


@dataclass(frozen=True)
class ExplanationResult:
    """Normalized Anthropic explanation response."""

    text: str
    model_used: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None


class AnthropicCallError(RuntimeError):
    """Safe wrapper for Anthropic API failures."""

    def __init__(self, reason: str, *, retryable: bool) -> None:
        """Create an error with a log-safe reason and retry hint."""
        super().__init__(reason)
        self.reason = reason
        self.retryable = retryable


class _MessagesClient(Protocol):
    async def create(self, **kwargs: Any) -> Any:
        """Create one Anthropic Messages response."""


class _AnthropicAsyncClient(Protocol):
    messages: _MessagesClient


class AnthropicClient:
    """Small async adapter around the official Anthropic SDK."""

    def __init__(
        self,
        api_key: str,
        *,
        fallback_model: str | None = None,
        retry_max: int = 1,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        client: _AnthropicAsyncClient | None = None,
    ) -> None:
        """Create an Anthropic client without exposing the API key in repr."""
        self._api_key = api_key
        self._fallback_model = fallback_model
        self._retry_max = retry_max
        self._sleep = sleep
        self._client = client or anthropic.AsyncAnthropic(api_key=api_key)

    def __repr__(self) -> str:
        """Return a repr with masked credentials."""
        return (
            "AnthropicClient(api_key=***, "
            f"fallback_model={self._fallback_model!r}, retry_max={self._retry_max})"
        )

    async def create_message(
        self,
        *,
        model: str,
        system: str,
        user: str,
        max_tokens: int,
        timeout: float,  # noqa: ASYNC109 - passed through to Anthropic SDK.
    ) -> ExplanationResult:
        """Call Anthropic Messages API and normalize text and usage fields."""
        attempts = [model]
        if self._retry_max > 0 and self._fallback_model:
            attempts.append(self._fallback_model)

        last_error: AnthropicCallError | None = None
        for index, attempt_model in enumerate(attempts):
            try:
                response = await self._client.messages.create(
                    model=attempt_model,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                    max_tokens=max_tokens,
                    timeout=timeout,
                )
                return _normalize_response(response, attempt_model)
            except Exception as exc:
                last_error = _map_error(exc)
                if index < len(attempts) - 1:
                    await self._sleep(0.5)

        assert last_error is not None
        raise last_error


def _normalize_response(response: Any, requested_model: str) -> ExplanationResult:
    """Convert an Anthropic SDK response into ExplanationResult."""
    text_parts = [
        str(block.text)
        for block in getattr(response, "content", [])
        if getattr(block, "type", None) == "text" and getattr(block, "text", None)
    ]
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)
    return ExplanationResult(
        text="\n".join(text_parts).strip(),
        model_used=str(getattr(response, "model", requested_model)),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=(
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None
        ),
    )


def _map_error(exc: Exception) -> AnthropicCallError:
    """Map SDK and transport errors into safe AnthropicCallError values."""
    retryable = isinstance(
        exc,
        (
            ConnectionError,
            TimeoutError,
            anthropic.APIConnectionError,
            anthropic.APITimeoutError,
            anthropic.APIStatusError,
        ),
    )
    reason = exc.__class__.__name__
    return AnthropicCallError(reason, retryable=retryable)
