"""canonicalize price snapshots

Revision ID: c0d2f8e4a9b1
Revises: a7c9f1d4e8b2
Create Date: 2026-05-19 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c0d2f8e4a9b1"
down_revision: Union[str, None] = "a7c9f1d4e8b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_price_snapshots_source_symbol_collected_at", table_name="price_snapshots")
    op.drop_index("ix_price_snapshots_collected_at", table_name="price_snapshots")
    op.alter_column(
        "price_snapshots",
        "symbol",
        new_column_name="asset",
        existing_type=sa.String(10),
        existing_nullable=False,
    )
    op.alter_column(
        "price_snapshots",
        "collected_at",
        new_column_name="ts",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "price_snapshots",
        "price",
        new_column_name="price_usd",
        existing_type=sa.Numeric(20, 8),
        existing_nullable=False,
    )
    op.create_index(
        "ix_price_snapshots_source_asset_ts",
        "price_snapshots",
        ["source", "asset", "ts"],
    )
    op.create_index("ix_price_snapshots_ts", "price_snapshots", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_price_snapshots_ts", table_name="price_snapshots")
    op.drop_index("ix_price_snapshots_source_asset_ts", table_name="price_snapshots")
    op.alter_column(
        "price_snapshots",
        "price_usd",
        new_column_name="price",
        existing_type=sa.Numeric(20, 8),
        existing_nullable=False,
    )
    op.alter_column(
        "price_snapshots",
        "ts",
        new_column_name="collected_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
    )
    op.alter_column(
        "price_snapshots",
        "asset",
        new_column_name="symbol",
        existing_type=sa.String(10),
        existing_nullable=False,
    )
    op.create_index(
        "ix_price_snapshots_source_symbol_collected_at",
        "price_snapshots",
        ["source", "symbol", "collected_at"],
    )
    op.create_index("ix_price_snapshots_collected_at", "price_snapshots", ["collected_at"])
