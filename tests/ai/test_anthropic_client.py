from types import SimpleNamespace
from typing import Any

import pytest

from duzman.ai.anthropic_client import AnthropicCallError, AnthropicClient


class FakeMessages:
    """Messages API test double."""

    def __init__(self, responses: list[object]) -> None:
        self.responses = responses
        self.calls: list[dict[str, object]] = []

    async def create(self, **kwargs: Any) -> Any:
        """Return or raise the next scripted response."""
        self.calls.append(kwargs)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeAnthropic:
    """Anthropic client test double."""

    messages: Any

    def __init__(self, responses: list[object]) -> None:
        self.messages = FakeMessages(responses)


@pytest.mark.asyncio
async def test_create_message_normalizes_text_and_usage() -> None:
    """Successful Messages responses should be normalized."""
    response = SimpleNamespace(
        model="claude-sonnet-4-6",
        content=[SimpleNamespace(type="text", text="explanation")],
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    fake = FakeAnthropic([response])
    client = AnthropicClient("secret", client=fake)

    result = await client.create_message(
        model="claude-sonnet-4-6",
        system="system",
        user="user",
        max_tokens=500,
        timeout=20,
    )

    assert result.text == "explanation"
    assert result.model_used == "claude-sonnet-4-6"
    assert result.input_tokens == 10
    assert result.output_tokens == 5
    assert result.total_tokens == 15
    assert fake.messages.calls[0]["messages"] == [{"role": "user", "content": "user"}]


@pytest.mark.asyncio
async def test_create_message_uses_fallback_after_primary_failure() -> None:
    """Primary model failures should retry once with the fallback model."""
    response = SimpleNamespace(
        model="claude-sonnet-4-5-20250929",
        content=[SimpleNamespace(type="text", text="fallback explanation")],
        usage=SimpleNamespace(input_tokens=4, output_tokens=6),
    )
    fake = FakeAnthropic([TimeoutError("temporary"), response])
    client = AnthropicClient(
        "secret",
        fallback_model="claude-sonnet-4-5-20250929",
        client=fake,
        sleep=_sleep,
    )

    result = await client.create_message(
        model="claude-sonnet-4-6",
        system="system",
        user="user",
        max_tokens=500,
        timeout=20,
    )

    assert result.text == "fallback explanation"
    assert [call["model"] for call in fake.messages.calls] == [
        "claude-sonnet-4-6",
        "claude-sonnet-4-5-20250929",
    ]


@pytest.mark.asyncio
async def test_create_message_raises_safe_error_after_failures() -> None:
    """Repeated failures should expose only a safe error reason."""
    fake = FakeAnthropic([TimeoutError("contains secret"), TimeoutError("contains secret")])
    client = AnthropicClient(
        "real-secret-value",
        fallback_model="claude-sonnet-4-5-20250929",
        client=fake,
        sleep=_sleep,
    )

    with pytest.raises(AnthropicCallError) as exc_info:
        await client.create_message(
            model="claude-sonnet-4-6",
            system="system",
            user="user",
            max_tokens=500,
            timeout=20,
        )

    assert exc_info.value.reason == "TimeoutError"
    assert exc_info.value.retryable is True
    assert "real-secret-value" not in repr(client)
    assert "real-secret-value" not in str(exc_info.value)


async def _sleep(_: float) -> None:
    """No-op async sleep for retry tests."""
