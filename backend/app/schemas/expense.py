from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ExpenseCreate(BaseModel):
    vendor_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    expense_date: datetime
    amount: float
    tax_amount: float = 0
    currency: str = "INR"
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class ExpenseUpdate(BaseModel):
    vendor_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    expense_date: Optional[datetime] = None
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    status: Optional[str] = None
    reference_number: Optional[str] = None
    notes: Optional[str] = None


class ExpenseResponse(BaseModel):
    id: str
    company_id: str
    vendor_id: Optional[str]
    title: str
    description: Optional[str]
    category: Optional[str]
    expense_date: datetime
    amount: float
    tax_amount: float
    total_amount: float
    currency: str
    status: str
    reference_number: Optional[str]
    notes: Optional[str]
    created_at: datetime
    vendor_name: Optional[str] = None

    model_config = {"from_attributes": True}
