from sqlalchemy import Column, String, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
import enum
from sqlalchemy import Enum as SAEnum
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
    STOCK_ITEMS = "stock_items"
    STOCK_CATEGORIES = "stock_categories"
    UNITS = "units"
    GODOWNS = "godowns"
    VOUCHERS = "vouchers"


class Upload(Base):
    __tablename__ = "uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    file_path = Column(String(500))
    file_size = Column(Integer)
    file_type = Column(String(50))
    upload_type = Column(SAEnum(UploadType))
    status = Column(SAEnum(UploadStatus), default=UploadStatus.PENDING)

    total_rows = Column(Integer, default=0)
    valid_rows = Column(Integer, default=0)
    invalid_rows = Column(Integer, default=0)
    duplicate_rows = Column(Integer, default=0)
    imported_rows = Column(Integer, default=0)

    error_summary = Column(JSONB)
    extracted_data = Column(JSONB)

    # Smart ingestion metadata
    detected_entity_type = Column(String(100), nullable=True)
    entity_confidence = Column(String(20), nullable=True)   # high | medium | low
    entity_subtype = Column(String(100), nullable=True)     # e.g. "Sales" for Voucher
    column_mapping = Column(JSONB, nullable=True)           # {file_col: schema_field}
    header_pattern_key = Column(String(64), nullable=True)  # MD5 fingerprint of sorted cols
    pending_rows = Column(JSONB, nullable=True)             # raw parsed rows from file
    row_report = Column(JSONB, nullable=True)               # [{row_id, status, errors, warnings, mapped}]
    commit_summary = Column(JSONB, nullable=True)           # {imported, tally_queued, errors}

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))

    company = relationship("Company", back_populates="uploads")


class UploadColumnCache(Base):
    """Persists confirmed column-mapping per company so repeat uploads skip detection."""
    __tablename__ = "upload_column_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    header_fingerprint = Column(String(64), nullable=False)   # MD5 of sorted, normalised column names
    entity_type = Column(String(100), nullable=False)
    column_mapping = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("company_id", "header_fingerprint", name="uq_col_cache_company_fp"),
    )
