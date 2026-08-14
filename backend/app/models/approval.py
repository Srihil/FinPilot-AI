from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class ApprovalStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ApprovalEntityType(str, enum.Enum):
    INVOICE = "invoice"
    EXPENSE = "expense"
    AI_TRANSACTION = "ai_transaction"


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    entity_type = Column(SAEnum(ApprovalEntityType), nullable=False)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"))
    expense_id = Column(UUID(as_uuid=True), ForeignKey("expenses.id"))

    # For AI-proposed transactions not yet linked to an entity
    proposed_data = Column(JSONB)
    ai_prompt = Column(Text)

    status = Column(SAEnum(ApprovalStatus), default=ApprovalStatus.PENDING)
    review_notes = Column(Text)

    requested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    reviewed_at = Column(DateTime(timezone=True))

    invoice = relationship("Invoice", back_populates="approval")
    expense = relationship("Expense", back_populates="approval")
    reviewed_by_user = relationship("User", back_populates="approvals", foreign_keys=[reviewed_by])
