import importlib
import sys


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
}


def test_model_metadata_contains_expected_stage_a_tables(monkeypatch, tmp_path):
    """Model metadata should load without connecting to PostgreSQL."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://duzman_app:PASSWORD@localhost:5432/duzman",
    )
    for module_name in (
        "duzman.db.models",
        "duzman.db.session",
        "duzman.settings",
    ):
        sys.modules.pop(module_name, None)

    session_module = importlib.import_module("duzman.db.session")
    importlib.import_module("duzman.db.models")

    assert EXPECTED_STAGE_A_TABLES <= set(session_module.Base.metadata.tables)

