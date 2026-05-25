"""Tests for the Issue #72 Stage A asset seed migration SQL invariant."""

from __future__ import annotations

import importlib
from typing import Any

from sqlalchemy.dialects import postgresql

from duzman.assets import STAGE_A_ASSETS

MIGRATION_MODULE = "duzman.db.alembic.versions.e6f4a9b2c1d3_seed_stage_a_assets"


class _OperationRecorder:
    """Capture Alembic execute calls without touching a database."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> None:
        self.statements.append(statement)


def test_seed_migration_sql_contains_all_stage_a_assets(monkeypatch):
    """The seed migration should insert exactly the canonical Stage A symbols."""
    sql = _compiled_upgrade_sql(monkeypatch)

    for symbol in STAGE_A_ASSETS:
        assert f"'{symbol}'" in sql
    assert sql.count("), (") == len(STAGE_A_ASSETS) - 1


def test_seed_migration_sql_is_idempotent(monkeypatch):
    """The seed migration should use PostgreSQL conflict handling."""
    sql = _compiled_upgrade_sql(monkeypatch)

    assert "ON CONFLICT (symbol) DO NOTHING" in sql


def test_seed_migration_sql_preserves_existing_btc_row(monkeypatch):
    """Existing BTC rows should be preserved by insert-only conflict handling."""
    sql = _compiled_upgrade_sql(monkeypatch)

    assert "'BTC'" in sql
    assert sql.startswith("INSERT INTO assets")
    assert " UPDATE " not in sql
    assert " DELETE " not in sql
    assert "ON CONFLICT (symbol) DO NOTHING" in sql


def _compiled_upgrade_sql(monkeypatch) -> str:
    """Compile the upgrade statement with PostgreSQL dialect in offline style."""
    migration = importlib.import_module(MIGRATION_MODULE)
    recorder = _OperationRecorder()
    monkeypatch.setattr(migration, "op", recorder)

    migration.upgrade()

    assert len(recorder.statements) == 1
    compiled = recorder.statements[0].compile(
        dialect=postgresql.dialect(),
        compile_kwargs={"literal_binds": True},
    )
    return str(compiled)
