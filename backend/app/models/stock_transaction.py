"""
Stock Transaction — records inventory movement entries in FinPilot.

Types supported:
  STOCK_JOURNAL    — transfer stock between godowns / adjust quantities
  PHYSICAL_STOCK   — physical stock count / verification entry
  DELIVERY_NOTE    — outward delivery (goods out, customer)
  RECEIPT_NOTE     — inward receipt (goods in, vendor)
  REJECTION_IN     — goods returned in (from customer)
  REJECTION_OUT    — goods rejected out (to vendor)

Note on TallyPrime sync:
  Tally stock transactions use TDL-based voucher types (Stock Journal, Delivery Note, etc.)
  These are NOT supported by the standard XML/TDL connector used in this project.
  Stock transactions are stored locally in FinPilot. If Tally sync is required,
  TDL voucher handlers must be added to the connector for each type.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSONB
from datetime import datetime, timezone
import uuid
from app.db.base import Base


class StockTransaction(Base):
    __tablename__ = "stock_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    transaction_number = Column(String(100), nullable=False)
    transaction_type = Column(String(50), nullable=False, index=True)
    # STOCK_JOURNAL | PHYSICAL_STOCK | DELIVERY_NOTE | RECEIPT_NOTE | REJECTION_IN | REJECTION_OUT

    transaction_date = Column(DateTime(timezone=True), nullable=True)
    narration = Column(Text, nullable=True)
    party_name = Column(String(500), nullable=True)  # customer/vendor for delivery/receipt notes
    from_godown = Column(String(500), nullable=True)
    to_godown = Column(String(500), nullable=True)

    entries = Column(JSONB, nullable=True)
    # List of: [{stock_item_name, quantity, unit, rate, godown}]

    tally_sync_status = Column(String(50), default="local_only")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
