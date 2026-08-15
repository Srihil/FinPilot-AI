from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class ExpenseStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAID = "PAID"


class ExpenseCategory(str, enum.Enum):
    OFFICE_SUPPLIES = "Office Supplies"
    UTILITIES = "Utilities"
    RENT = "Rent"
    SALARIES = "Salaries"
    TRAVEL = "Travel"
    MARKETING = "Marketing"
    SOFTWARE = "Software"
    EQUIPMENT = "Equipment"
    MAINTENANCE = "Maintenance"
    PROFESSIONAL_SERVICES = "Professional Services"
    RAW_MATERIALS = "Raw Materials"
    SHIPPING = "Shipping"
    INSURANCE = "Insurance"
    TAXES = "Taxes"
    MISCELLANEOUS = "Miscellaneous"


class Expense(Base):
    __tablename__ = "expenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    title = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    expense_date = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    tax_amount = Column(Numeric(15, 2), default=0)
    total_amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), default="INR")
    status = Column(SAEnum(ExpenseStatus), default=ExpenseStatus.DRAFT)
    reference_number = Column(String(100))
    receipt_path = Column(String(500))
    notes = Column(Text)

    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at = Column(DateTime(timezone=True))

    is_deleted = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="expenses")
    vendor = relationship("Vendor", back_populates="expenses")
    approval = relationship("Approval", back_populates="expense", uselist=False)
