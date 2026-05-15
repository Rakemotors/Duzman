"""normalize price snapshots

Revision ID: 2b8f4f6c9a1e
Revises: b009e25bfab4
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2b8f4f6c9a1e"
down_revision: Union[str, None] = "b009e25bfab4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_price_snapshots_ts_asset", table_name="price_snapshots")
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
    op.alter_column(
        "price_snapshots",
        "price_usd",
        new_column_name="price",
        existing_type=sa.Numeric(20, 8),
        existing_nullable=True,
        nullable=False,
    )
    op.alter_column(
        "price_snapshots",
        "volume_24h_usd",
        new_column_name="volume_24h_quote",
        existing_type=sa.Numeric(20, 2),
        existing_nullable=True,
    )
    op.alter_column(
        "price_snapshots",
        "source",
        existing_type=sa.String(20),
        existing_nullable=True,
        nullable=False,
    )
    op.add_column(
        "price_snapshots",
        sa.Column("quote_currency", sa.String(10), nullable=False, server_default="USD"),
    )
    op.alter_column(
        "price_snapshots",
        "quote_currency",
        existing_type=sa.String(10),
        server_default=None,
    )
    op.add_column(
        "price_snapshots",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.add_column("price_snapshots", sa.Column("raw_payload", sa.JSON(), nullable=True))
    op.drop_column("price_snapshots", "price_change_7d_pct")
    op.create_index(
        "ix_price_snapshots_source_symbol_collected_at",
        "price_snapshots",
        ["source", "symbol", "collected_at"],
    )
    op.create_index(
        "ix_price_snapshots_collected_at",
        "price_snapshots",
        ["collected_at"],
    )
    op.create_index("ix_price_snapshots_source", "price_snapshots", ["source"])


def downgrade() -> None:
    op.drop_index("ix_price_snapshots_source", table_name="price_snapshots")
    op.drop_index("ix_price_snapshots_collected_at", table_name="price_snapshots")
    op.drop_index(
        "ix_price_snapshots_source_symbol_collected_at",
        table_name="price_snapshots",
    )
    op.add_column(
        "price_snapshots",
        sa.Column("price_change_7d_pct", sa.Numeric(8, 4), nullable=True),
    )
    op.drop_column("price_snapshots", "raw_payload")
    op.drop_column("price_snapshots", "created_at")
    op.drop_column("price_snapshots", "quote_currency")
    op.alter_column(
        "price_snapshots",
        "source",
        existing_type=sa.String(20),
        existing_nullable=False,
        nullable=True,
    )
    op.alter_column(
        "price_snapshots",
        "volume_24h_quote",
        new_column_name="volume_24h_usd",
        existing_type=sa.Numeric(20, 2),
        existing_nullable=True,
    )
    op.alter_column(
        "price_snapshots",
        "price",
        new_column_name="price_usd",
        existing_type=sa.Numeric(20, 8),
        existing_nullable=False,
        nullable=True,
    )
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
    op.create_index("ix_price_snapshots_ts_asset", "price_snapshots", ["ts", "asset"])
