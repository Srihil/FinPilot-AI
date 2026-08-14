from sqlalchemy import Column, String, DateTime, ForeignKey, Numeric, Text, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class PaymentMethod(str, enum.Enum):
    CASH = "Cash"
    BANK_TRANSFER = "Bank Transfer"
    CHEQUE = "Cheque"
    UPI = "UPI"
    CREDIT_CARD = "Credit Card"
    DEBIT_CARD = "Debit Card"
    NEFT = "NEFT"
    RTGS = "RTGS"
    OTHER = "Other"


class PaymentType(str, enum.Enum):
    RECEIVED = "RECEIVED"   # payment from customer
    MADE = "MADE"           # payment to vendor


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id"))
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    payment_type = Column(SAEnum(PaymentType), nullable=False)
    payment_date = Column(DateTime(timezone=True), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    currency = Column(String(10), default="INR")
    payment_method = Column(SAEnum(PaymentMethod), default=PaymentMethod.BANK_TRANSFER)
    reference_number = Column(String(100))
    notes = Column(Text)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="payments")
    invoice = relationship("Invoice", back_populates="payments")
    customer = relationship("Customer", back_populates="payments")
    vendor = relationship("Vendor", back_populates="payments")
