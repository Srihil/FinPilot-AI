from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, Text, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class UploadStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class UploadType(str, enum.Enum):
    CUSTOMERS = "customers"
    VENDORS = "vendors"
    PRODUCTS = "products"
    INVOICES = "invoices"
    EXPENSES = "expenses"
    PAYMENTS = "payments"
    INVOICE_PDF = "invoice_pdf"
    LEDGERS = "ledgers"
    STOCK_GROUPS = "stock_groups"
    UNITS = "units"
    GODOWNS = "godowns"


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    file_path = Column(String(500))
    file_size = Column(Integer)
    file_type = Column(String(50))  # csv, xlsx, pdf
    upload_type = Column(SAEnum(UploadType))
    status = Column(SAEnum(UploadStatus), default=UploadStatus.PENDING)

    total_rows = Column(Integer, default=0)
    valid_rows = Column(Integer, default=0)
    invalid_rows = Column(Integer, default=0)
    duplicate_rows = Column(Integer, default=0)
    imported_rows = Column(Integer, default=0)

    error_summary = Column(JSONB)
    extracted_data = Column(JSONB)  # for PDF extractions

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))

    company = relationship("Company", back_populates="uploads")
