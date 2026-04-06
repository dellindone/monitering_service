import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Float, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum as SAEnum
from core.database import Base
from engine.trade_state import TradeState


class Trade(Base):
    __tablename__ = "trades"

    id              = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    symbol          = Column(String, nullable=False)
    quantity        = Column(Float, nullable=False)
    buy_price       = Column(Float, nullable=False)
    sl_price        = Column(Float, nullable=False)
    current_price   = Column(Float, nullable=True)
    pnl             = Column(Float, nullable=True)
    state           = Column(SAEnum(TradeState), nullable=False)
    source          = Column(String, default="WEBSOCKET")  # WEBSOCKET | EXTERNAL
    broker_order_id = Column(String, nullable=True)
    created_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at      = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))


class DailyStat(Base):
    __tablename__ = "daily_stats"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date         = Column(String, nullable=False, unique=True)
    realized_pnl = Column(Float, default=0.0)
    trade_count  = Column(Float, default=0)
    is_halted    = Column(String, default="false")
    summary_sent = Column(String, default="false")
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
