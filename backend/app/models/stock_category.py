"""
Stock Category — an additional classification layer for stock items in FinPilot.

Note: TallyPrime has a concept of "Stock Categories" but it is NOT part of the standard
XML/TDL export/import used by this connector. Stock categories are tracked locally in
FinPilot for filtering and reporting. They do NOT sync to TallyPrime automatically.
If TallyPrime stock category sync is required, TDL must be implemented in the connector.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
from app.db.base import Base


class StockCategory(Base):
    __tablename__ = "stock_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    parent = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    tally_key = Column(String(512), nullable=True)
    source = Column(String(50), default="finpilot")
    tally_job_id = Column(UUID(as_uuid=True), nullable=True)
    tally_sync_status = Column(String(50), default="pending")
    synced_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
