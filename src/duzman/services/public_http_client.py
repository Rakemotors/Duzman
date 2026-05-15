import logging
from typing import Any, Mapping
from urllib.parse import urlsplit

import httpx

from duzman.logging_config import get_logger, log_event


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
        self.logger = get_logger(__name__)

    def get_json(
        self,
        url: str,
        params: Mapping[str, str] | None = None,
    ) -> Any:
        """Fetch public JSON over GET without credentials or private headers."""
        host, path = self._safe_url_parts(url)
        log_event(self.logger, "public_http_get_started", host=host, path=path)
        try:
            response = self._client.get(
                url,
                params=dict(params or {}),
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            log_event(
                self.logger,
                "public_http_get_failed",
                level=logging.ERROR,
                host=host,
                path=path,
                error_type=type(exc).__name__,
                safe_error_message="public request timed out",
            )
            raise PublicHttpTimeoutError("Public HTTP request timed out") from exc
        except httpx.HTTPError as exc:
            log_event(
                self.logger,
                "public_http_get_failed",
                level=logging.ERROR,
                host=host,
                path=path,
                error_type=type(exc).__name__,
                safe_error_message="public request failed",
            )
            raise PublicHttpNetworkError("Public HTTP request failed") from exc

        if not 200 <= response.status_code < 300:
            log_event(
                self.logger,
                "public_http_get_failed",
                level=logging.ERROR,
                host=host,
                path=path,
                status_code=response.status_code,
            )
            raise PublicHttpStatusError(
                f"Public HTTP request returned status {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            log_event(
                self.logger,
                "public_http_get_failed",
                level=logging.ERROR,
                host=host,
                path=path,
                error_type=type(exc).__name__,
                safe_error_message="public response was not valid JSON",
            )
            raise PublicHttpJsonError("Public HTTP response was not valid JSON") from exc

        log_event(
            self.logger,
            "public_http_get_succeeded",
            host=host,
            path=path,
            status_code=response.status_code,
        )
        return payload

    def _safe_url_parts(self, url: str) -> tuple[str, str]:
        parsed_url = urlsplit(url)
        return parsed_url.netloc, parsed_url.path or "/"
