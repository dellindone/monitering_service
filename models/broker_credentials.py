import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from core.database import Base


class BrokerCredential(Base):
    __tablename__ = "broker_credentials"

    id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_name = Column(String, nullable=False)  # "groww" | "zerodha" | "upstox"
    is_active   = Column(Boolean, default=False, nullable=False)
    credentials = Column(JSONB, nullable=False)               # broker-specific fields as JSON
    created_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at  = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                         onupdate=lambda: datetime.now(timezone.utc))
