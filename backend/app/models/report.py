from sqlalchemy import Column, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class ReportType(str, enum.Enum):
    PROFIT_LOSS = "profit_loss"
    REVENUE = "revenue"
    EXPENSE = "expense"
    RECEIVABLES = "receivables"
    PAYABLES = "payables"
    CUSTOMER_REVENUE = "customer_revenue"
    VENDOR_SPENDING = "vendor_spending"
    INVENTORY = "inventory"
    MONTHLY_SUMMARY = "monthly_summary"
    CASH_FLOW = "cash_flow"
    GST_SUMMARY = "gst_summary"
    TRIAL_BALANCE = "trial_balance"
    AGED_RECEIVABLES = "aged_receivables"
    AGED_PAYABLES = "aged_payables"
    CUSTOMER_STATEMENT = "customer_statement"
    VENDOR_STATEMENT = "vendor_statement"


class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    report_type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    parameters = Column(JSONB)
    file_path = Column(String(500))
    ai_insights = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="reports")
