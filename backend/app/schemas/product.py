from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ProductCreate(BaseModel):
    sku: Optional[str] = None
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    unit: str = "pcs"
    purchase_price: float = 0
    selling_price: float = 0
    tax_rate: float = 18.0
    stock_quantity: float = 0
    reorder_threshold: float = 10
    track_inventory: bool = True


class ProductUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    unit: Optional[str] = None
    purchase_price: Optional[float] = None
    selling_price: Optional[float] = None
    tax_rate: Optional[float] = None
    stock_quantity: Optional[float] = None
    reorder_threshold: Optional[float] = None
    is_active: Optional[bool] = None
    track_inventory: Optional[bool] = None


class ProductResponse(BaseModel):
    id: str
    company_id: str
    sku: Optional[str]
    name: str
    description: Optional[str]
    category: Optional[str]
    unit: str
    purchase_price: float
    selling_price: float
    tax_rate: float
    stock_quantity: float
    reorder_threshold: float
    is_active: bool
    track_inventory: bool
    created_at: datetime
    inventory_value: Optional[float] = 0
    is_low_stock: Optional[bool] = False

    model_config = {"from_attributes": True}
