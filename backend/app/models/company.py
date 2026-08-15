from sqlalchemy import Column, String, Boolean, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
from app.db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    legal_name = Column(String(255))
    gst_number = Column(String(50))
    pan_number = Column(String(20))
    address = Column(Text)
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100), default="India")
    pincode = Column(String(20))
    phone = Column(String(50))
    email = Column(String(255))
    website = Column(String(255))
    currency = Column(String(10), default="INR")
    fiscal_year_start = Column(String(10), default="04-01")  # MM-DD
    ai_provider = Column(String(20), nullable=True)  # overrides env var when set
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    users = relationship("User", back_populates="company")
    customers = relationship("Customer", back_populates="company")
    vendors = relationship("Vendor", back_populates="company")
    products = relationship("Product", back_populates="company")
    accounts = relationship("Account", back_populates="company")
    invoices = relationship("Invoice", back_populates="company")
    expenses = relationship("Expense", back_populates="company")
    payments = relationship("Payment", back_populates="company")
    uploads = relationship("Upload", back_populates="company")
    audit_logs = relationship("AuditLog", back_populates="company")
    reports = relationship("Report", back_populates="company")
    ai_conversations = relationship("AIConversation", back_populates="company")
