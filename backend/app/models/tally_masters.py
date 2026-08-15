from sqlalchemy import Column, String, Float, Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from app.db.types import CompatibleJSON as JSON
from datetime import datetime, timezone
import uuid
from app.db.base import Base


class TallyLedger(Base):
    __tablename__ = "tally_ledgers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    parent_group = Column(String(255), nullable=True)
    opening_balance = Column(Float, default=0.0)
    conflict_data = Column(JSON, nullable=True)
    conflict_detected_at = Column(DateTime(timezone=True), nullable=True)
    closing_balance = Column(Float, default=0.0)
    tally_key = Column(String(512), nullable=False)  # name-based dedup key per company
    source = Column(String(50), default="tally_sync")  # "tally_sync" | "finpilot"
    tally_job_id = Column(UUID(as_uuid=True), nullable=True)
    tally_sync_status = Column(String(50), default="pending")  # pending | synced | failed
    synced_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TallyStockGroup(Base):
    __tablename__ = "tally_stock_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    parent = Column(String(255), nullable=True)
    tally_key = Column(String(512), nullable=False)
    source = Column(String(50), default="tally_sync")
    tally_job_id = Column(UUID(as_uuid=True), nullable=True)
    tally_sync_status = Column(String(50), default="pending")
    synced_at = Column(DateTime(timezone=True), nullable=True)
    conflict_data = Column(JSON, nullable=True)
    conflict_detected_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TallyUnit(Base):
    __tablename__ = "tally_units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    symbol = Column(String(20), nullable=True)
    decimal_places = Column(Integer, default=0)
    unit_type = Column(String(20), default="simple")
    tally_key = Column(String(512), nullable=False)
    source = Column(String(50), default="tally_sync")
    tally_job_id = Column(UUID(as_uuid=True), nullable=True)
    tally_sync_status = Column(String(50), default="pending")
    synced_at = Column(DateTime(timezone=True), nullable=True)
    conflict_data = Column(JSON, nullable=True)
    conflict_detected_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TallyGodown(Base):
    __tablename__ = "tally_godowns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    parent = Column(String(255), nullable=True)
    tally_key = Column(String(512), nullable=False)
    source = Column(String(50), default="tally_sync")
    tally_job_id = Column(UUID(as_uuid=True), nullable=True)
    tally_sync_status = Column(String(50), default="pending")
    synced_at = Column(DateTime(timezone=True), nullable=True)
    conflict_data = Column(JSON, nullable=True)
    conflict_detected_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))


class TallyGroup(Base):
    """Accounting group in TallyPrime (e.g., Sundry Debtors, Capital Account, Bank Accounts)."""
    __tablename__ = "tally_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(500), nullable=False)
    parent = Column(String(255), nullable=True)
    nature = Column(String(50), nullable=True)
    tally_key = Column(String(512), nullable=False)
    source = Column(String(50), default="tally_sync")
    tally_job_id = Column(UUID(as_uuid=True), nullable=True)
    tally_sync_status = Column(String(50), default="pending")
    synced_at = Column(DateTime(timezone=True), nullable=True)
    conflict_data = Column(JSON, nullable=True)
    conflict_detected_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))
