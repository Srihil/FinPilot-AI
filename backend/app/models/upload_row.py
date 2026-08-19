from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class UploadRowStatus(str, enum.Enum):
    PENDING  = "pending"
    IMPORTED = "imported"
    FAILED   = "failed"


class UploadRow(Base):
    __tablename__ = "upload_rows"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    upload_id    = Column(UUID(as_uuid=True), ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True)
    row_number   = Column(Integer, nullable=False)
    entity_type  = Column(String(100))
    status       = Column(SAEnum(UploadRowStatus), default=UploadRowStatus.PENDING, index=True)
    error_reason = Column(Text, nullable=True)
    raw_data     = Column(JSONB)
    tally_job_id = Column(UUID(as_uuid=True), ForeignKey("tally_integration_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
