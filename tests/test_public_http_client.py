import httpx
import pytest

from duzman.services import (
    PublicHttpClient,
    PublicHttpJsonError,
    PublicHttpNetworkError,
    PublicHttpStatusError,
    PublicHttpTimeoutError,
)


def test_public_http_client_returns_json_from_successful_get():
    """The public HTTP client should parse JSON from a successful GET."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"ok": True})
    )
    client = PublicHttpClient(client=httpx.Client(transport=transport))

    payload = client.get_json("https://example.test/public", {"symbol": "BTCUSDT"})

    assert payload == {"ok": True}


def test_public_http_client_raises_for_non_2xx_response():
    """Non-2xx public responses should raise a clear status error."""
    transport = httpx.MockTransport(lambda request: httpx.Response(503, json={}))
    client = PublicHttpClient(client=httpx.Client(transport=transport))

    with pytest.raises(PublicHttpStatusError, match="503"):
        client.get_json("https://example.test/public")


def test_public_http_client_raises_for_timeout():
    """Timeouts should raise a dedicated timeout error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    client = PublicHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(PublicHttpTimeoutError, match="timed out"):
        client.get_json("https://example.test/public")


def test_public_http_client_raises_for_network_failure():
    """Transport failures should raise a dedicated network error."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    client = PublicHttpClient(client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(PublicHttpNetworkError, match="failed"):
        client.get_json("https://example.test/public")


def test_public_http_client_raises_for_invalid_json():
    """Invalid JSON bodies should raise a clear JSON error."""
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"not-json")
    )
    client = PublicHttpClient(client=httpx.Client(transport=transport))

    with pytest.raises(PublicHttpJsonError, match="not valid JSON"):
        client.get_json("https://example.test/public")
