# src/duzman/db/alembic/versions/e6f4a9b2c1d3_seed_stage_a_assets.py
# Alembic seed migration for canonical Stage A asset rows.

"""Seed canonical Stage A assets idempotently for Issue #72.

The upgrade uses PostgreSQL `ON CONFLICT DO NOTHING`, so existing asset rows
are preserved and only missing canonical Stage A symbols are inserted.
Downgrade is intentionally a no-op because deleting seed rows could orphan
FK-referenced rows in asset-scoped tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import insert as pg_insert

from duzman.assets import STAGE_A_ASSET_NAMES, STAGE_A_ASSETS

# revision identifiers, used by Alembic.
revision: str = "e6f4a9b2c1d3"
down_revision: str | None = "9b7c6d5e4f3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Insert missing canonical Stage A assets without replacing existing rows."""
    assets_table = sa.table(
        "assets",
        sa.column("symbol", sa.String),
        sa.column("name", sa.String),
        sa.column("enabled", sa.Boolean),
    )
    rows = [
        {
            "symbol": symbol,
            "name": STAGE_A_ASSET_NAMES[symbol],
            "enabled": True,
        }
        for symbol in STAGE_A_ASSETS
    ]
    statement = pg_insert(assets_table).values(rows)
    statement = statement.on_conflict_do_nothing(index_elements=["symbol"])
    op.execute(statement)


def downgrade() -> None:
    """Leave seeded assets in place to avoid orphaning FK-referenced rows."""
    # Seed downgrade could orphan rows in indicators, price_snapshots,
    # funding_rates, open_interest, long_short_ratio, liquidations,
    # liquidation_heatmap, and pattern_triggers.
