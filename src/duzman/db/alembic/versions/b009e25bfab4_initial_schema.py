"""initial schema

Revision ID: b009e25bfab4
Revises:
Create Date: 2026-05-14 10:29:49.796770

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, JSONB
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b009e25bfab4'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("symbol", sa.String(10), primary_key=True),
        sa.Column("name", sa.String(50), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("price_usd", sa.Numeric(20, 8), nullable=True),
        sa.Column("volume_24h_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("price_change_24h_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("price_change_7d_pct", sa.Numeric(8, 4), nullable=True),
        sa.Column("source", sa.String(20), nullable=True),
    )
    op.create_index("ix_price_snapshots_ts_asset", "price_snapshots", ["ts", "asset"])

    op.create_table(
        "indicators",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("indicator_type", sa.String(20), nullable=False),
        sa.Column("timeframe", sa.String(10), nullable=True),
        sa.Column("value", sa.Numeric(12, 4), nullable=True),
        sa.Column("parameters", JSONB(), nullable=True),
    )
    op.create_index(
        "ix_indicators_ts_asset_type_tf",
        "indicators",
        ["ts", "asset", "indicator_type", "timeframe"],
    )

    op.create_table(
        "funding_rates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("funding_rate_pct", sa.Numeric(10, 6), nullable=True),
        sa.Column("next_funding_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("predicted_rate", sa.Numeric(10, 6), nullable=True),
    )
    op.create_index("ix_funding_rates_ts_asset", "funding_rates", ["ts", "asset"])

    op.create_table(
        "open_interest",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("oi_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("oi_contracts", sa.Numeric(20, 2), nullable=True),
    )
    op.create_index("ix_open_interest_ts_asset", "open_interest", ["ts", "asset"])

    op.create_table(
        "long_short_ratio",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("exchange", sa.String(20), nullable=False),
        sa.Column("ratio_type", sa.String(30), nullable=False),
        sa.Column("long_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("short_pct", sa.Numeric(6, 2), nullable=True),
        sa.Column("ratio", sa.Numeric(10, 4), nullable=True),
    )

    op.create_table(
        "liquidations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("longs_liquidated_1h_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("shorts_liquidated_1h_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("longs_liquidated_24h_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("shorts_liquidated_24h_usd", sa.Numeric(20, 2), nullable=True),
    )

    op.create_table(
        "etf_flows",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("asset", sa.String(10), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("flow_usd_m", sa.Numeric(10, 2), nullable=True),
        sa.PrimaryKeyConstraint("date", "asset", "provider"),
    )

    op.create_table(
        "global_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric_name", sa.String(30), nullable=False),
        sa.Column("value", sa.Numeric(12, 4), nullable=True),
    )

    op.create_table(
        "pattern_triggers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pattern_name", sa.String(50), nullable=False),
        sa.Column("asset", sa.String(10), sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("conditions_snapshot", JSONB(), nullable=True),
        sa.Column("ai_explanation", sa.Text(), nullable=True),
        sa.Column("alert_sent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("user_feedback", sa.String(20), nullable=True),
        sa.Column("user_feedback_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "alerts_sent",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "pattern_trigger_id",
            sa.BigInteger(),
            sa.ForeignKey("pattern_triggers.id"),
            nullable=False,
        ),
        sa.Column(
            "sent_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("delivery_status", sa.String(20), nullable=False),
        sa.Column("delivery_error", sa.Text(), nullable=True),
        sa.Column("dedup_key", sa.String(100), nullable=False),
    )
    op.create_index(
        "ix_alerts_sent_dedup_key_sent_at", "alerts_sent", ["dedup_key", "sent_at"]
    )

    op.create_table(
        "api_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("endpoint", sa.String(100), nullable=True),
        sa.Column("ip_address", INET(), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
    )

    op.create_table(
        "source_health",
        sa.Column("source", sa.String(20), primary_key=True),
        sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("source_health")
    op.drop_table("api_requests")
    op.drop_index("ix_alerts_sent_dedup_key_sent_at", table_name="alerts_sent")
    op.drop_table("alerts_sent")
    op.drop_table("pattern_triggers")
    op.drop_table("global_metrics")
    op.drop_table("etf_flows")
    op.drop_table("liquidations")
    op.drop_table("long_short_ratio")
    op.drop_index("ix_open_interest_ts_asset", table_name="open_interest")
    op.drop_table("open_interest")
    op.drop_index("ix_funding_rates_ts_asset", table_name="funding_rates")
    op.drop_table("funding_rates")
    op.drop_index("ix_indicators_ts_asset_type_tf", table_name="indicators")
    op.drop_table("indicators")
    op.drop_index("ix_price_snapshots_ts_asset", table_name="price_snapshots")
    op.drop_table("price_snapshots")
    op.drop_table("assets")
