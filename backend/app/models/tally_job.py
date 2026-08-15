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
    # Accounting master writes
    CREATE_LEDGER = "CREATE_LEDGER"
    CREATE_GROUP = "CREATE_GROUP"
    # Inventory master writes
    CREATE_STOCK_ITEM = "CREATE_STOCK_ITEM"
    CREATE_STOCK_GROUP = "CREATE_STOCK_GROUP"
    CREATE_UNIT = "CREATE_UNIT"
    CREATE_GODOWN = "CREATE_GODOWN"
    # Voucher type
    CREATE_VOUCHER_TYPE = "CREATE_VOUCHER_TYPE"
    # Voucher writes
    CREATE_SALES_VOUCHER = "CREATE_SALES_VOUCHER"
    CREATE_PURCHASE_VOUCHER = "CREATE_PURCHASE_VOUCHER"
    CREATE_RECEIPT_VOUCHER = "CREATE_RECEIPT_VOUCHER"
    CREATE_PAYMENT_VOUCHER = "CREATE_PAYMENT_VOUCHER"
    CREATE_JOURNAL_VOUCHER = "CREATE_JOURNAL_VOUCHER"
    CREATE_CREDIT_NOTE = "CREATE_CREDIT_NOTE"
    CREATE_DEBIT_NOTE = "CREATE_DEBIT_NOTE"
    CREATE_CONTRA_VOUCHER = "CREATE_CONTRA_VOUCHER"
    # Delete operations
    DELETE_LEDGER = "DELETE_LEDGER"
    DELETE_STOCK_ITEM = "DELETE_STOCK_ITEM"
    DELETE_STOCK_GROUP = "DELETE_STOCK_GROUP"
    DELETE_UNIT = "DELETE_UNIT"
    DELETE_GODOWN = "DELETE_GODOWN"
    # Voucher cancel (Tally-confirmed-first)
    CANCEL_VOUCHER = "CANCEL_VOUCHER"
    # Sync
    SYNC_FULL = "SYNC_FULL"
    SYNC_PARTIAL = "SYNC_PARTIAL"


DELETE_OPERATIONS = {
    TallyJobOperation.DELETE_LEDGER,
    TallyJobOperation.DELETE_STOCK_ITEM,
    TallyJobOperation.DELETE_STOCK_GROUP,
    TallyJobOperation.DELETE_UNIT,
    TallyJobOperation.DELETE_GODOWN,
}

WRITE_OPERATIONS = {
    TallyJobOperation.CREATE_LEDGER,
    TallyJobOperation.CREATE_GROUP,
    TallyJobOperation.CREATE_STOCK_ITEM,
    TallyJobOperation.CREATE_STOCK_GROUP,
    TallyJobOperation.CREATE_UNIT,
    TallyJobOperation.CREATE_GODOWN,
    TallyJobOperation.CREATE_VOUCHER_TYPE,
    TallyJobOperation.CREATE_SALES_VOUCHER,
    TallyJobOperation.CREATE_PURCHASE_VOUCHER,
    TallyJobOperation.CREATE_RECEIPT_VOUCHER,
    TallyJobOperation.CREATE_PAYMENT_VOUCHER,
    TallyJobOperation.CREATE_JOURNAL_VOUCHER,
    TallyJobOperation.CREATE_CREDIT_NOTE,
    TallyJobOperation.CREATE_DEBIT_NOTE,
    TallyJobOperation.CREATE_CONTRA_VOUCHER,
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
