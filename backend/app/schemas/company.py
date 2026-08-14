from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime


class CompanyCreate(BaseModel):
    name: str
    legal_name: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "India"
    pincode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    currency: str = "INR"
    fiscal_year_start: str = "04-01"


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    legal_name: Optional[str] = None
    gst_number: Optional[str] = None
    pan_number: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    pincode: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    currency: Optional[str] = None
    fiscal_year_start: Optional[str] = None


class CompanyResponse(BaseModel):
    id: str
    name: str
    legal_name: Optional[str]
    gst_number: Optional[str]
    pan_number: Optional[str]
    address: Optional[str]
    city: Optional[str]
    state: Optional[str]
    country: str
    currency: str
    fiscal_year_start: str
    phone: Optional[str]
    email: Optional[str]
    website: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}
