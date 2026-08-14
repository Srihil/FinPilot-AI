from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
import enum
from app.db.base import Base


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    CANCELLED = "CANCELLED"


class TallyJobOperation(str, enum.Enum):
    # Read operations
    READ_COMPANIES = "READ_COMPANIES"
    READ_LEDGERS = "READ_LEDGERS"
    READ_VOUCHERS = "READ_VOUCHERS"
    READ_SALES = "READ_SALES"
    READ_PURCHASES = "READ_PURCHASES"
    READ_RECEIVABLES = "READ_RECEIVABLES"
    READ_PAYABLES = "READ_PAYABLES"
    READ_STOCK_ITEMS = "READ_STOCK_ITEMS"
    # Write operations (require prior approval)
    CREATE_SALES_VOUCHER = "CREATE_SALES_VOUCHER"
    CREATE_PURCHASE_VOUCHER = "CREATE_PURCHASE_VOUCHER"
    CREATE_RECEIPT_VOUCHER = "CREATE_RECEIPT_VOUCHER"
    CREATE_PAYMENT_VOUCHER = "CREATE_PAYMENT_VOUCHER"
    CREATE_LEDGER = "CREATE_LEDGER"
    CREATE_STOCK_ITEM = "CREATE_STOCK_ITEM"
    # Sync
    SYNC_FULL = "SYNC_FULL"
    SYNC_PARTIAL = "SYNC_PARTIAL"


WRITE_OPERATIONS = {
    TallyJobOperation.CREATE_SALES_VOUCHER,
    TallyJobOperation.CREATE_PURCHASE_VOUCHER,
    TallyJobOperation.CREATE_RECEIPT_VOUCHER,
    TallyJobOperation.CREATE_PAYMENT_VOUCHER,
    TallyJobOperation.CREATE_LEDGER,
    TallyJobOperation.CREATE_STOCK_ITEM,
}


class TallyIntegrationJob(Base):
    __tablename__ = "tally_integration_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    connector_id = Column(UUID(as_uuid=True), ForeignKey("tally_connectors.id"), nullable=True, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approval_id = Column(UUID(as_uuid=True), ForeignKey("approvals.id"), nullable=True)  # required for write ops

    operation = Column(SAEnum(TallyJobOperation), nullable=False)
    payload = Column(JSONB)       # input params for the operation
    result = Column(JSONB)        # output from TallyPrime
    status = Column(SAEnum(JobStatus), default=JobStatus.PENDING, index=True)
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)
    idempotency_key = Column(String(255), unique=True, index=True)  # prevents duplicate writes

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    claimed_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    company = relationship("Company")
    connector = relationship("TallyConnector", back_populates="jobs")
