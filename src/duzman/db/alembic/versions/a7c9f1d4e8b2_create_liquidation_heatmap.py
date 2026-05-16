"""create liquidation heatmap

Revision ID: a7c9f1d4e8b2
Revises: 5c1c8f9d0e2a
Create Date: 2026-05-16 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a7c9f1d4e8b2"
down_revision: Union[str, None] = "5c1c8f9d0e2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "liquidation_heatmap",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=False),
        sa.Column("price_low", sa.Numeric(20, 8), nullable=False),
        sa.Column("price_high", sa.Numeric(20, 8), nullable=False),
        sa.Column("liquidation_volume_usd", sa.Numeric(20, 2), nullable=False),
    )
    op.create_index(
        "ix_liquidation_heatmap_ts_asset_tf",
        "liquidation_heatmap",
        ["ts", "asset", "timeframe"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_liquidation_heatmap_ts_asset_tf",
        table_name="liquidation_heatmap",
    )
    op.drop_table("liquidation_heatmap")
