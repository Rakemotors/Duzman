# tests/health/test_app.py
# Endpoint checks for the local health liveness FastAPI app.
# Covers the health response shape and default unknown-route behavior.
"""Endpoint tests for the local health service."""

from datetime import datetime

from fastapi.testclient import TestClient

from duzman.health.app import app


def test_health_returns_200_with_expected_shape() -> None:
    """Health should return liveness status, package version, and UTC timestamp."""
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert set(response.json()) == {"status", "version", "ts"}
    assert response.json()["status"] == "ok"
    assert isinstance(response.json()["version"], str)
    assert response.json()["version"]
    timestamp = datetime.fromisoformat(response.json()["ts"])
    assert timestamp.tzinfo is not None


def test_unknown_path_returns_404() -> None:
    """Unknown paths should keep FastAPI 404s and trailing health slash redirects."""
    client = TestClient(app)

    unknown_response = client.get("/foo")
    trailing_slash_response = client.get("/health/", follow_redirects=False)

    assert unknown_response.status_code == 404
    assert unknown_response.json() == {"detail": "Not Found"}
    assert trailing_slash_response.status_code == 307
