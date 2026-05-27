# tests/health/test_app.py
# Endpoint checks for the local health liveness FastAPI app.
# Covers health response shape, build metadata, and unknown-route behavior.
"""Endpoint tests for the local health service."""

from datetime import datetime

from fastapi.testclient import TestClient

from duzman.health.app import app, get_build_sha


def test_health_returns_200_with_expected_shape(monkeypatch, tmp_path) -> None:
    """Health should return liveness status, package version, build SHA, and UTC timestamp."""
    monkeypatch.delenv("DUZMAN_BUILD_SHA", raising=False)
    monkeypatch.setenv("DUZMAN_BUILD_SHA_PATH", str(tmp_path / "BUILD_SHA"))

    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert set(response.json()) == {"status", "version", "build_sha", "ts"}
    assert response.json()["status"] == "ok"
    assert isinstance(response.json()["version"], str)
    assert response.json()["version"]
    assert response.json()["build_sha"] == "unknown"
    timestamp = datetime.fromisoformat(response.json()["ts"])
    assert timestamp.tzinfo is not None


def test_build_sha_reads_local_file_before_environment(monkeypatch, tmp_path) -> None:
    """Build SHA should prefer explicit local build metadata over env fallback."""
    monkeypatch.setenv("DUZMAN_BUILD_SHA", "env-sha")
    build_sha_path = tmp_path / "BUILD_SHA"
    monkeypatch.setenv("DUZMAN_BUILD_SHA_PATH", str(build_sha_path))
    build_sha_path.write_text("file-sha\n", encoding="utf-8")

    assert get_build_sha() == "file-sha"


def test_build_sha_uses_environment_when_file_is_missing(monkeypatch, tmp_path) -> None:
    """Build SHA should use process environment when no local build file exists."""
    monkeypatch.setenv("DUZMAN_BUILD_SHA", "env-sha")
    monkeypatch.setenv("DUZMAN_BUILD_SHA_PATH", str(tmp_path / "BUILD_SHA"))

    assert get_build_sha() == "env-sha"


def test_build_sha_returns_unknown_when_unavailable(monkeypatch, tmp_path) -> None:
    """Missing build metadata should not fail health checks."""
    monkeypatch.delenv("DUZMAN_BUILD_SHA", raising=False)
    monkeypatch.setenv("DUZMAN_BUILD_SHA_PATH", str(tmp_path / "BUILD_SHA"))

    assert get_build_sha() == "unknown"


def test_build_sha_resolves_independently_of_cwd(monkeypatch, tmp_path) -> None:
    """Build SHA should not read BUILD_SHA from the process working directory."""
    monkeypatch.delenv("DUZMAN_BUILD_SHA", raising=False)
    monkeypatch.delenv("DUZMAN_BUILD_SHA_PATH", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "BUILD_SHA").write_text("cwd-should-not-be-read\n", encoding="utf-8")

    assert get_build_sha() != "cwd-should-not-be-read"


def test_unknown_path_returns_404() -> None:
    """Unknown paths should keep FastAPI 404s and trailing health slash redirects."""
    client = TestClient(app)

    unknown_response = client.get("/foo")
    trailing_slash_response = client.get("/health/", follow_redirects=False)

    assert unknown_response.status_code == 404
    assert unknown_response.json() == {"detail": "Not Found"}
    assert trailing_slash_response.status_code == 307
