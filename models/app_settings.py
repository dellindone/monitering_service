import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, Float, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from core.database import Base


class AppSettings(Base):
    __tablename__ = "app_settings"

    id                          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Risk
    daily_loss_limit            = Column(Float, default=5000.0)
    daily_target                = Column(Float, default=10000.0)

    # Capital
    capital_index_option        = Column(Float, default=50000.0)
    capital_stock_option        = Column(Float, default=25000.0)

    # Lot size multipliers
    lot_size_multiplier_nifty     = Column(Integer, default=1)
    lot_size_multiplier_banknifty = Column(Integer, default=1)
    lot_size_multiplier_sensex    = Column(Integer, default=1)
    lot_size_multiplier_stock     = Column(Integer, default=1)

    # External scan
    external_scan_interval      = Column(Integer, default=30)

    updated_at                  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                                         onupdate=lambda: datetime.now(timezone.utc))
