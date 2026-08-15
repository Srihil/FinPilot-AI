from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    order_number = Column(String(100), nullable=False)
    order_type = Column(String(20), nullable=False)   # SALES | PURCHASE
    party_name = Column(String(500), nullable=True)
    party_ledger = Column(String(500), nullable=True)
    order_date = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    total_amount = Column(Numeric(15, 2), default=0)
    narration = Column(Text, nullable=True)
    status = Column(String(30), default="DRAFT")   # DRAFT | CONFIRMED | FULFILLED | CANCELLED
    tally_sync_status = Column(String(50), default="local_only")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False, index=True)
    stock_item_name = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    quantity = Column(Numeric(15, 3), default=1)
    unit = Column(String(50), nullable=True)
    unit_price = Column(Numeric(15, 2), default=0)
    amount = Column(Numeric(15, 2), default=0)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    order = relationship("Order", back_populates="items")
