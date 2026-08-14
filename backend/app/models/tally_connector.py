from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Integer, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class ConnectorStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    DISCONNECTED = "DISCONNECTED"
    REVOKED = "REVOKED"


class TallyConnector(Base):
    __tablename__ = "tally_connectors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    connector_name = Column(String(255))           # human label e.g. "Office PC"
    device_name = Column(String(255))              # Windows hostname
    token_hash = Column(String(255), nullable=False, unique=True)  # bcrypt-hashed connector token
    status = Column(SAEnum(ConnectorStatus), default=ConnectorStatus.ACTIVE)
    tally_host = Column(String(255), default="localhost")
    tally_port = Column(Integer, default=9000)
    tally_company_name = Column(String(500))       # the open Tally company, from last heartbeat
    last_heartbeat = Column(DateTime(timezone=True))
    last_sync_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime(timezone=True))

    company = relationship("Company")
    jobs = relationship("TallyIntegrationJob", back_populates="connector")


class TallyPairingCode(Base):
    __tablename__ = "tally_pairing_codes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code = Column(String(20), nullable=False, unique=True, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True))
    is_used = Column(Boolean, default=False)

    company = relationship("Company")
