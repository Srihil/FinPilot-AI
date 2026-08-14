from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from fastapi import HTTPException
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.schemas.customer import CustomerCreate, CustomerUpdate
from typing import Optional
import uuid


class CustomerService:
    def get_all(self, db: Session, company_id: uuid.UUID, search: Optional[str] = None,
                page: int = 1, page_size: int = 20):
        query = db.query(Customer).filter(Customer.company_id == company_id, Customer.is_active == True)
        if search:
            query = query.filter(
                Customer.name.ilike(f"%{search}%") |
                Customer.email.ilike(f"%{search}%") |
                Customer.phone.ilike(f"%{search}%")
            )
        total = query.count()
        items = query.order_by(Customer.name).offset((page - 1) * page_size).limit(page_size).all()

        result = []
        for c in items:
            total_revenue = db.query(func.sum(Invoice.total_amount)).filter(
                Invoice.customer_id == c.id,
                Invoice.invoice_type == InvoiceType.SALES,
                Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID])
            ).scalar() or 0

            outstanding = db.query(func.sum(Invoice.total_amount - Invoice.paid_amount)).filter(
                Invoice.customer_id == c.id,
                Invoice.invoice_type == InvoiceType.SALES,
                Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE])
            ).scalar() or 0

            c.total_revenue = float(total_revenue)
            c.outstanding_balance = float(outstanding)
            result.append(c)

        return result, total

    def get_by_id(self, db: Session, company_id: uuid.UUID, customer_id: str) -> Customer:
        customer = db.query(Customer).filter(
            Customer.id == uuid.UUID(customer_id),
            Customer.company_id == company_id
        ).first()
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    def create(self, db: Session, company_id: uuid.UUID, data: CustomerCreate) -> Customer:
        customer = Customer(company_id=company_id, **data.model_dump())
        db.add(customer)
        db.commit()
        db.refresh(customer)
        return customer

    def update(self, db: Session, company_id: uuid.UUID, customer_id: str, data: CustomerUpdate) -> Customer:
        customer = self.get_by_id(db, company_id, customer_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(customer, field, value)
        db.commit()
        db.refresh(customer)
        return customer

    def delete(self, db: Session, company_id: uuid.UUID, customer_id: str) -> None:
        customer = self.get_by_id(db, company_id, customer_id)
        customer.is_active = False
        db.commit()


customer_service = CustomerService()
