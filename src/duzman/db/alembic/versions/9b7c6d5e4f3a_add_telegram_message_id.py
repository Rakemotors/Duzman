"""Add Telegram base message id to alert deliveries."""

import sqlalchemy as sa
from alembic import op

revision = "9b7c6d5e4f3a"
down_revision = "8f3a2c1b9d6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add nullable Telegram message id for explanation replies."""
    op.add_column(
        "alert_deliveries",
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    """Drop Telegram message id from alert deliveries."""
    op.drop_column("alert_deliveries", "telegram_message_id")
