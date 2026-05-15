import importlib
import sys

import pytest


EXPECTED_STAGE_A_TABLES = {
    "assets",
    "price_snapshots",
    "indicators",
    "funding_rates",
    "open_interest",
    "long_short_ratio",
    "liquidations",
    "etf_flows",
    "global_metrics",
    "pattern_triggers",
    "alerts_sent",
    "api_requests",
    "source_health",
    "source_health_checks",
}


def test_model_metadata_contains_expected_stage_a_tables(monkeypatch, tmp_path):
    """Model metadata should load without connecting to PostgreSQL."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for module_name in (
        "duzman.db.models",
        "duzman.db.session",
        "duzman.settings",
    ):
        sys.modules.pop(module_name, None)

    session_module = importlib.import_module("duzman.db.session")
    importlib.import_module("duzman.db.models")

    assert EXPECTED_STAGE_A_TABLES <= set(session_module.Base.metadata.tables)


def test_database_engine_requires_database_url(monkeypatch, tmp_path):
    """Opening a DB engine should fail clearly when DATABASE_URL is absent."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for module_name in ("duzman.db.session", "duzman.settings"):
        sys.modules.pop(module_name, None)

    session_module = importlib.import_module("duzman.db.session")

    with pytest.raises(RuntimeError, match="DATABASE_URL must be configured"):
        session_module.get_engine()
