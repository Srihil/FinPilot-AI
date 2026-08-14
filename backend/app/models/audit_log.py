from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class AuditAction(str, enum.Enum):
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    UPLOAD = "UPLOAD"
    DOWNLOAD = "DOWNLOAD"
    GENERATE_REPORT = "GENERATE_REPORT"
    AI_QUERY = "AI_QUERY"
    AI_PROPOSAL = "AI_PROPOSAL"
    SETTINGS_CHANGE = "SETTINGS_CHANGE"
    INTEGRATION_SYNC = "INTEGRATION_SYNC"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"
    USER_INVITE = "USER_INVITE"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), index=True)

    action = Column(SAEnum(AuditAction), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(UUID(as_uuid=True))
    description = Column(Text)
    extra_data = Column(JSONB)  # renamed from 'metadata' (reserved by SQLAlchemy)
    ip_address = Column(String(50))
    user_agent = Column(String(500))
    status = Column(String(50), default="SUCCESS")

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    company = relationship("Company", back_populates="audit_logs")
    user = relationship("User", back_populates="audit_logs")
