"""create source health checks

Revision ID: 5c1c8f9d0e2a
Revises: 2b8f4f6c9a1e
Create Date: 2026-05-15 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5c1c8f9d0e2a"
down_revision: Union[str, None] = "2b8f4f6c9a1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "source_health_checks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_source_health_checks_source_checked_at",
        "source_health_checks",
        ["source", "checked_at"],
    )
    op.create_index(
        "ix_source_health_checks_status",
        "source_health_checks",
        ["status"],
    )
    op.create_index(
        "ix_source_health_checks_checked_at",
        "source_health_checks",
        ["checked_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_health_checks_checked_at",
        table_name="source_health_checks",
    )
    op.drop_index(
        "ix_source_health_checks_status",
        table_name="source_health_checks",
    )
    op.drop_index(
        "ix_source_health_checks_source_checked_at",
        table_name="source_health_checks",
    )
    op.drop_table("source_health_checks")

