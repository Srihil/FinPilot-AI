from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Text, Integer, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    SENT = "SENT"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    CANCELLED = "CANCELLED"


class InvoiceType(str, enum.Enum):
    SALES = "SALES"
    PURCHASE = "PURCHASE"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    vendor_id = Column(UUID(as_uuid=True), ForeignKey("vendors.id"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    invoice_number = Column(String(100), nullable=False)
    invoice_type = Column(SAEnum(InvoiceType), default=InvoiceType.SALES)
    status = Column(SAEnum(InvoiceStatus), default=InvoiceStatus.DRAFT)

    invoice_date = Column(DateTime(timezone=True), nullable=False)
    due_date = Column(DateTime(timezone=True))

    subtotal = Column(Numeric(15, 2), default=0)
    tax_amount = Column(Numeric(15, 2), default=0)
    discount_amount = Column(Numeric(15, 2), default=0)
    total_amount = Column(Numeric(15, 2), default=0)
    paid_amount = Column(Numeric(15, 2), default=0)

    currency = Column(String(10), default="INR")
    notes = Column(Text)
    terms = Column(Text)

    # AI extraction metadata
    extracted_from_document = Column(Boolean, default=False)
    source_document_path = Column(String(500))

    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at = Column(DateTime(timezone=True))

    is_deleted = Column(Boolean, default=False)

    # TallyPrime sync tracking (added for Tally-confirmed-first delete)
    tally_voucher_ref = Column(String(100), nullable=True)   # REMOTEID sent to Tally (FP-xxxx)
    tally_sync_status = Column(String(50), default="local_only")
    # local_only | pending | synced | failed | delete_pending | delete_failed

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="invoices")
    customer = relationship("Customer", back_populates="invoices")
    vendor = relationship("Vendor")
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="invoice")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"))

    description = Column(String(500), nullable=False)
    quantity = Column(Numeric(15, 3), default=1)
    unit_price = Column(Numeric(15, 2), default=0)
    tax_rate = Column(Numeric(5, 2), default=0)
    tax_amount = Column(Numeric(15, 2), default=0)
    discount_rate = Column(Numeric(5, 2), default=0)
    discount_amount = Column(Numeric(15, 2), default=0)
    line_total = Column(Numeric(15, 2), default=0)

    invoice = relationship("Invoice", back_populates="items")
    product = relationship("Product", back_populates="invoice_items")
