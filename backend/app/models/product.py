from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Numeric, Text, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid
from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    sku = Column(String(100))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    category = Column(String(100))
    unit = Column(String(50), default="pcs")
    purchase_price = Column(Numeric(15, 2), default=0)
    selling_price = Column(Numeric(15, 2), default=0)
    tax_rate = Column(Numeric(5, 2), default=18.0)  # GST percentage
    stock_quantity = Column(Numeric(15, 3), default=0)
    reorder_threshold = Column(Numeric(15, 3), default=10)
    is_active = Column(Boolean, default=True)
    track_inventory = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    company = relationship("Company", back_populates="products")
    invoice_items = relationship("InvoiceItem", back_populates="product")
    inventory_transactions = relationship("InventoryTransaction", back_populates="product")
