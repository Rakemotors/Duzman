import importlib

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from duzman.db.session import Base


def _migration_schema() -> tuple[
    dict[str, list[sa.Column]], set[tuple[str, str, tuple[str, ...]]]
]:
    """Build a lightweight schema by capturing Alembic operations offline."""
    migrations = [
        importlib.import_module(
            "duzman.db.alembic.versions.b009e25bfab4_initial_schema"
        ),
        importlib.import_module(
            "duzman.db.alembic.versions.2b8f4f6c9a1e_normalize_price_snapshots"
        ),
        importlib.import_module(
            "duzman.db.alembic.versions.5c1c8f9d0e2a_create_source_health_checks"
        ),
        importlib.import_module(
            "duzman.db.alembic.versions.a7c9f1d4e8b2_create_liquidation_heatmap"
        ),
        importlib.import_module(
            "duzman.db.alembic.versions.c0d2f8e4a9b1_canonicalize_price_snapshots"
        ),
        importlib.import_module(
            "duzman.db.alembic.versions.d7e1f2a3b4c5_add_alert_deliveries_and_telegram_state"
        ),
    ]
    tables: dict[str, list[sa.Column]] = {}
    indexes: set[tuple[str, str, tuple[str, ...]]] = set()

    class OperationRecorder:
        """Record migration operations without touching a database."""

        def create_table(self, name, *elements, **kwargs):
            primary_key_columns = {
                column_name
                for element in elements
                if isinstance(element, sa.PrimaryKeyConstraint)
                for column_name in (
                    element.columns.keys()
                    or getattr(element, "_pending_colargs", ())
                )
            }
            tables[name] = []
            for element in elements:
                if not isinstance(element, sa.Column):
                    continue
                tables[name].append(
                    sa.Column(
                        element.name,
                        element.type,
                        primary_key=element.primary_key
                        or element.name in primary_key_columns,
                        nullable=element.nullable,
                    )
                )

        def create_index(self, name, table_name, columns, **kwargs):
            indexes.add((name, table_name, tuple(columns)))

        def drop_index(self, name, table_name, **kwargs):
            indexes.difference_update(
                [
                    index
                    for index in indexes
                    if index[0] == name and index[1] == table_name
                ]
            )

        def add_column(self, table_name, column):
            tables[table_name].append(column)

        def drop_column(self, table_name, column_name):
            tables[table_name] = [
                column for column in tables[table_name] if column.name != column_name
            ]

        def alter_column(
            self,
            table_name,
            column_name,
            new_column_name=None,
            existing_type=None,
            nullable=None,
            **kwargs,
        ):
            replacement_columns = []
            for column in tables[table_name]:
                if column.name != column_name:
                    replacement_columns.append(column)
                    continue
                replacement_columns.append(
                    sa.Column(
                        new_column_name or column.name,
                        existing_type or column.type,
                        primary_key=column.primary_key,
                        nullable=column.nullable if nullable is None else nullable,
                    )
                )
            tables[table_name] = replacement_columns

    recorder = OperationRecorder()
    for migration in migrations:
        original_op = migration.op
        migration.op = recorder
        try:
            migration.upgrade()
        finally:
            migration.op = original_op

    return tables, indexes


def _column_signature(column: sa.Column) -> tuple[str, str, bool, bool]:
    """Return the schema fields expected to match between ORM and migration."""
    return (
        column.name,
        column.type.compile(dialect=postgresql.dialect()),
        column.nullable,
        column.primary_key,
    )


def test_orm_tables_match_migration_chain_tables():
    """The ORM and migration chain should declare the same Stage A tables."""
    importlib.import_module("duzman.db.models")

    migration_tables, _ = _migration_schema()

    assert set(Base.metadata.tables) == set(migration_tables)


def test_orm_columns_match_migration_chain_columns():
    """Core column names, types, nullability, and primary keys should match."""
    importlib.import_module("duzman.db.models")

    migration_tables, _ = _migration_schema()

    for table_name, orm_table in Base.metadata.tables.items():
        orm_columns = sorted(_column_signature(column) for column in orm_table.columns)
        migration_columns = [
            _column_signature(column) for column in migration_tables[table_name]
        ]

        assert orm_columns == sorted(migration_columns)


def test_orm_indexes_match_migration_chain_indexes():
    """Indexes declared in ORM metadata should be present in the migration."""
    importlib.import_module("duzman.db.models")

    _, migration_indexes = _migration_schema()
    orm_indexes = {
        (index.name, index.table.name, tuple(column.name for column in index.columns))
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }

    assert orm_indexes <= migration_indexes
