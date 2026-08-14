from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException
from app.models.vendor import Vendor
from app.models.expense import Expense, ExpenseStatus
from app.models.invoice import Invoice, InvoiceType, InvoiceStatus
from app.schemas.vendor import VendorCreate, VendorUpdate
from typing import Optional
import uuid


class VendorService:
    def get_all(self, db: Session, company_id: uuid.UUID, search: Optional[str] = None,
                page: int = 1, page_size: int = 20):
        query = db.query(Vendor).filter(Vendor.company_id == company_id, Vendor.is_active == True)
        if search:
            query = query.filter(
                Vendor.name.ilike(f"%{search}%") |
                Vendor.email.ilike(f"%{search}%")
            )
        total = query.count()
        items = query.order_by(Vendor.name).offset((page - 1) * page_size).limit(page_size).all()

        result = []
        for v in items:
            total_purchases = db.query(func.sum(Expense.total_amount)).filter(
                Expense.vendor_id == v.id,
                Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID])
            ).scalar() or 0

            outstanding = db.query(func.sum(Invoice.total_amount - Invoice.paid_amount)).filter(
                Invoice.vendor_id == v.id,
                Invoice.invoice_type == InvoiceType.PURCHASE,
                Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID])
            ).scalar() or 0

            v.total_purchases = float(total_purchases)
            v.outstanding_payable = float(outstanding)
            result.append(v)

        return result, total

    def get_by_id(self, db: Session, company_id: uuid.UUID, vendor_id: str) -> Vendor:
        vendor = db.query(Vendor).filter(
            Vendor.id == uuid.UUID(vendor_id),
            Vendor.company_id == company_id
        ).first()
        if not vendor:
            raise HTTPException(status_code=404, detail="Vendor not found")
        return vendor

    def create(self, db: Session, company_id: uuid.UUID, data: VendorCreate) -> Vendor:
        vendor = Vendor(company_id=company_id, **data.model_dump())
        db.add(vendor)
        db.commit()
        db.refresh(vendor)
        return vendor

    def update(self, db: Session, company_id: uuid.UUID, vendor_id: str, data: VendorUpdate) -> Vendor:
        vendor = self.get_by_id(db, company_id, vendor_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(vendor, field, value)
        db.commit()
        db.refresh(vendor)
        return vendor

    def delete(self, db: Session, company_id: uuid.UUID, vendor_id: str) -> None:
        vendor = self.get_by_id(db, company_id, vendor_id)
        vendor.is_active = False
        db.commit()


vendor_service = VendorService()
