from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from duzman.db.session import Base


class Asset(Base):
    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now
    )


class PriceSnapshot(Base):
    __tablename__ = "price_snapshots"
    __table_args__ = (
        Index(
            "ix_price_snapshots_source_asset_ts",
            "source",
            "asset",
            "ts",
        ),
        Index("ix_price_snapshots_ts", "ts"),
        Index("ix_price_snapshots_source", "source"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(10), nullable=False)
    price_usd: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    volume_24h_quote: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    price_change_24h_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))


class Indicator(Base):
    __tablename__ = "indicators"
    __table_args__ = (
        Index("ix_indicators_ts_asset_type_tf", "ts", "asset", "indicator_type", "timeframe"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    indicator_type: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    parameters: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)


class FundingRate(Base):
    __tablename__ = "funding_rates"
    __table_args__ = (
        Index("ix_funding_rates_ts_asset", "ts", "asset"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    funding_rate_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6))
    next_funding_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    predicted_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 6), nullable=True)


class OpenInterest(Base):
    __tablename__ = "open_interest"
    __table_args__ = (
        Index("ix_open_interest_ts_asset", "ts", "asset"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    oi_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    oi_contracts: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))


class LongShortRatio(Base):
    __tablename__ = "long_short_ratio"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    ratio_type: Mapped[str] = mapped_column(String(30), nullable=False)
    long_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    short_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    ratio: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))


class Liquidation(Base):
    __tablename__ = "liquidations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    longs_liquidated_1h_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    shorts_liquidated_1h_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    longs_liquidated_24h_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    shorts_liquidated_24h_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))


class LiquidationHeatmap(Base):
    __tablename__ = "liquidation_heatmap"
    __table_args__ = (
        Index(
            "ix_liquidation_heatmap_ts_asset_tf",
            "ts",
            "asset",
            "timeframe",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    price_low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price_high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    liquidation_volume_usd: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)


class EtfFlow(Base):
    __tablename__ = "etf_flows"

    date: Mapped[date] = mapped_column(Date, nullable=False, primary_key=True)
    asset: Mapped[str] = mapped_column(String(10), nullable=False, primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False, primary_key=True)
    flow_usd_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))


class GlobalMetric(Base):
    __tablename__ = "global_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(30), nullable=False)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))


class PatternTrigger(Base):
    __tablename__ = "pattern_triggers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pattern_name: Mapped[str] = mapped_column(String(50), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    conditions_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    alert_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    user_feedback: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    user_feedback_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AlertSent(Base):
    __tablename__ = "alerts_sent"
    __table_args__ = (
        Index("ix_alerts_sent_dedup_key_sent_at", "dedup_key", "sent_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pattern_trigger_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pattern_triggers.id"), nullable=False
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.now
    )
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dedup_key: Mapped[str] = mapped_column(String(100), nullable=False)


class AlertDelivery(Base):
    __tablename__ = "alert_deliveries"
    __table_args__ = (
        UniqueConstraint("alert_id", "channel", name="uq_alert_deliveries_alert_channel"),
        Index("ix_alert_deliveries_alert_id_channel", "alert_id", "channel"),
        Index("ix_alert_deliveries_status_channel", "status", "channel"),
        Index("ix_alert_deliveries_sent_at", "sent_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    alert_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pattern_triggers.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ack_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    snooze_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TelegramChannelState(Base):
    __tablename__ = "telegram_channel_state"
    __table_args__ = (CheckConstraint("id = 1", name="ck_telegram_channel_state_singleton"),)

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    snooze_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AlertExplanation(Base):
    __tablename__ = "alert_explanations"
    __table_args__ = (
        Index(
            "uq_alert_explanations_pattern_trigger_id",
            "pattern_trigger_id",
            unique=True,
        ),
        Index("ix_alert_explanations_status_created_at", "status", "created_at"),
        Index("ix_alert_explanations_cache_key_created_at", "cache_key", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    pattern_trigger_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pattern_triggers.id", ondelete="CASCADE"), nullable=False
    )
    alert_delivery_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("alert_deliveries.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_context_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiRequest(Base):
    __tablename__ = "api_requests"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.now)
    endpoint: Mapped[Optional[str]] = mapped_column(String(100))
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    response_code: Mapped[Optional[int]] = mapped_column(Integer)
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)


class SourceHealth(Base):
    __tablename__ = "source_health"

    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    last_success: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False)


class SourceHealthCheck(Base):
    __tablename__ = "source_health_checks"
    __table_args__ = (
        Index("ix_source_health_checks_source_checked_at", "source", "checked_at"),
        Index("ix_source_health_checks_status", "status"),
        Index("ix_source_health_checks_checked_at", "checked_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
