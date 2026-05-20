"""Add Telegram delivery state tables."""

import sqlalchemy as sa
from alembic import op

revision = "d7e1f2a3b4c5"
down_revision = "c0d2f8e4a9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create alert delivery and Telegram channel state tables."""
    op.create_table(
        "alert_deliveries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snooze_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["alert_id"], ["pattern_triggers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_id", "channel", name="uq_alert_deliveries_alert_channel"),
    )
    op.create_index(
        "ix_alert_deliveries_alert_id_channel",
        "alert_deliveries",
        ["alert_id", "channel"],
    )
    op.create_index(
        "ix_alert_deliveries_status_channel",
        "alert_deliveries",
        ["status", "channel"],
    )
    op.create_index(
        "ix_alert_deliveries_sent_at",
        "alert_deliveries",
        ["sent_at"],
    )
    op.create_table(
        "telegram_channel_state",
        sa.Column("id", sa.SmallInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("snooze_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_telegram_channel_state_singleton"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop Telegram delivery state tables."""
    op.drop_table("telegram_channel_state")
    op.drop_index("ix_alert_deliveries_sent_at", table_name="alert_deliveries")
    op.drop_index("ix_alert_deliveries_status_channel", table_name="alert_deliveries")
    op.drop_index("ix_alert_deliveries_alert_id_channel", table_name="alert_deliveries")
    op.drop_table("alert_deliveries")
