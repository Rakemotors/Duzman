"""Add alert explanations table."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op


revision = "8f3a2c1b9d6e"
down_revision = "d7e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create AI explanation persistence table and indexes."""
    op.create_table(
        "alert_explanations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pattern_trigger_id", sa.BigInteger(), nullable=False),
        sa.Column("alert_delivery_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("prompt_context_json", postgresql.JSONB(), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["alert_delivery_id"],
            ["alert_deliveries.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["pattern_trigger_id"],
            ["pattern_triggers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_alert_explanations_pattern_trigger_id",
        "alert_explanations",
        ["pattern_trigger_id"],
        unique=True,
    )
    op.create_index(
        "ix_alert_explanations_status_created_at",
        "alert_explanations",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_alert_explanations_cache_key_created_at",
        "alert_explanations",
        ["cache_key", "created_at"],
    )


def downgrade() -> None:
    """Drop AI explanation persistence table and indexes."""
    op.drop_index(
        "ix_alert_explanations_cache_key_created_at",
        table_name="alert_explanations",
    )
    op.drop_index(
        "ix_alert_explanations_status_created_at",
        table_name="alert_explanations",
    )
    op.drop_index(
        "uq_alert_explanations_pattern_trigger_id",
        table_name="alert_explanations",
    )
    op.drop_table("alert_explanations")
