from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class InvoiceItemCreate(BaseModel):
    product_id: Optional[str] = None
    description: str
    quantity: float = 1
    unit_price: float
    tax_rate: float = 0
    discount_rate: float = 0


class InvoiceItemResponse(BaseModel):
    id: str
    invoice_id: str
    product_id: Optional[str]
    description: str
    quantity: float
    unit_price: float
    tax_rate: float
    tax_amount: float
    discount_rate: float
    discount_amount: float
    line_total: float

    model_config = {"from_attributes": True}


class InvoiceCreate(BaseModel):
    customer_id: Optional[str] = None
    vendor_id: Optional[str] = None
    invoice_number: str
    invoice_type: str = "SALES"
    invoice_date: datetime
    due_date: Optional[datetime] = None
    currency: str = "INR"
    notes: Optional[str] = None
    terms: Optional[str] = None
    items: List[InvoiceItemCreate] = []


class InvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None
    terms: Optional[str] = None
    status: Optional[str] = None
    items: Optional[List[InvoiceItemCreate]] = None


class InvoiceResponse(BaseModel):
    id: str
    company_id: str
    customer_id: Optional[str]
    vendor_id: Optional[str]
    invoice_number: str
    invoice_type: str
    status: str
    invoice_date: datetime
    due_date: Optional[datetime]
    subtotal: float
    tax_amount: float
    discount_amount: float
    total_amount: float
    paid_amount: float
    currency: str
    notes: Optional[str]
    created_at: datetime
    items: List[InvoiceItemResponse] = []
    customer_name: Optional[str] = None
    vendor_name: Optional[str] = None

    model_config = {"from_attributes": True}
