import importlib

import sqlalchemy as sa

from duzman.db.session import Base


def _migration_metadata() -> tuple[sa.MetaData, set[tuple[str, str, tuple[str, ...]]]]:
    """Build SQLAlchemy metadata by capturing the initial Alembic operations."""
    migration = importlib.import_module(
        "duzman.db.alembic.versions.b009e25bfab4_initial_schema"
    )
    metadata = sa.MetaData()
    indexes: set[tuple[str, str, tuple[str, ...]]] = set()

    class OperationRecorder:
        """Record create_table and create_index calls without touching a database."""

        def create_table(self, name, *elements, **kwargs):
            return sa.Table(name, metadata, *elements, **kwargs)

        def create_index(self, name, table_name, columns, **kwargs):
            indexes.add((name, table_name, tuple(columns)))

    original_op = migration.op
    migration.op = OperationRecorder()
    try:
        migration.upgrade()
    finally:
        migration.op = original_op

    return metadata, indexes


def _column_signature(column: sa.Column) -> tuple[str, str, bool, bool]:
    """Return the schema fields expected to match between ORM and migration."""
    return (
        column.name,
        column.type.compile(dialect=sa.dialects.postgresql.dialect()),
        column.nullable,
        column.primary_key,
    )


def test_orm_tables_match_initial_migration_tables():
    """The ORM and initial migration should declare the same Stage A tables."""
    importlib.import_module("duzman.db.models")

    migration_metadata, _ = _migration_metadata()

    assert set(Base.metadata.tables) == set(migration_metadata.tables)


def test_orm_columns_match_initial_migration_columns():
    """Core column names, types, nullability, and primary keys should match."""
    importlib.import_module("duzman.db.models")

    migration_metadata, _ = _migration_metadata()

    for table_name, orm_table in Base.metadata.tables.items():
        migration_table = migration_metadata.tables[table_name]
        orm_columns = [_column_signature(column) for column in orm_table.columns]
        migration_columns = [
            _column_signature(column) for column in migration_table.columns
        ]

        assert orm_columns == migration_columns


def test_orm_indexes_match_initial_migration_indexes():
    """Indexes declared in ORM metadata should be present in the migration."""
    importlib.import_module("duzman.db.models")

    _, migration_indexes = _migration_metadata()
    orm_indexes = {
        (index.name, index.table.name, tuple(column.name for column in index.columns))
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }

    assert orm_indexes <= migration_indexes

