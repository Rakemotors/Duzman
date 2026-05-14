from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Index, Integer,
    Numeric, String, Text, ForeignKey,
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
        Index("ix_price_snapshots_ts_asset", "ts", "asset"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    asset: Mapped[str] = mapped_column(String(10), ForeignKey("assets.symbol"), nullable=False)
    price_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 8))
    volume_24h_usd: Mapped[Optional[Decimal]] = mapped_column(Numeric(20, 2))
    price_change_24h_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    price_change_7d_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 4))
    source: Mapped[Optional[str]] = mapped_column(String(20))


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
