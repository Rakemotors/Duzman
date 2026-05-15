from typing import Any, Mapping

import httpx


class PublicHttpClientError(Exception):
    """Base error for public HTTP client failures."""


class PublicHttpNetworkError(PublicHttpClientError):
    """Raised when a public HTTP request fails before receiving a response."""


class PublicHttpTimeoutError(PublicHttpNetworkError):
    """Raised when a public HTTP request exceeds the configured timeout."""


class PublicHttpStatusError(PublicHttpClientError):
    """Raised when a public HTTP response is not successful."""


class PublicHttpJsonError(PublicHttpClientError):
    """Raised when a public HTTP response body is not valid JSON."""


class PublicHttpClient:
    """Small GET-only HTTP client for public market data endpoints."""

    def __init__(
        self,
        timeout_seconds: float = 10.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        """Fetch public JSON over GET without credentials or private headers."""
        try:
            response = self._client.get(
                url,
                params=dict(params or {}),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise PublicHttpTimeoutError("Public HTTP request timed out") from exc
        except httpx.HTTPError as exc:
            raise PublicHttpNetworkError("Public HTTP request failed") from exc

        if not 200 <= response.status_code < 300:
            raise PublicHttpStatusError(
                f"Public HTTP request returned status {response.status_code}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise PublicHttpJsonError("Public HTTP response was not valid JSON") from exc

