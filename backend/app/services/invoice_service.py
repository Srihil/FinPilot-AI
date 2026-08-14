from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from fastapi import HTTPException
from app.models.invoice import Invoice, InvoiceItem, InvoiceStatus, InvoiceType
from app.models.product import Product
from app.models.approval import Approval, ApprovalEntityType, ApprovalStatus
from app.models.audit_log import AuditLog, AuditAction
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate
from decimal import Decimal
from typing import Optional
import uuid
from datetime import datetime, timezone


class InvoiceService:
    def _compute_items(self, db: Session, items_data: list, company_id: uuid.UUID) -> tuple:
        items = []
        subtotal = Decimal("0")
        tax_total = Decimal("0")
        discount_total = Decimal("0")

        for item_data in items_data:
            qty = Decimal(str(item_data.quantity))
            unit_price = Decimal(str(item_data.unit_price))
            tax_rate = Decimal(str(item_data.tax_rate))
            discount_rate = Decimal(str(item_data.discount_rate))

            line_base = qty * unit_price
            discount_amount = line_base * discount_rate / 100
            taxable = line_base - discount_amount
            tax_amount = taxable * tax_rate / 100
            line_total = taxable + tax_amount

            subtotal += line_base
            discount_total += discount_amount
            tax_total += tax_amount

            item = InvoiceItem(
                product_id=uuid.UUID(item_data.product_id) if item_data.product_id else None,
                description=item_data.description,
                quantity=qty,
                unit_price=unit_price,
                tax_rate=tax_rate,
                tax_amount=tax_amount,
                discount_rate=discount_rate,
                discount_amount=discount_amount,
                line_total=line_total,
            )
            items.append(item)

        return items, subtotal, tax_total, discount_total

    def get_all(self, db: Session, company_id: uuid.UUID, page: int = 1, page_size: int = 20,
                status: Optional[str] = None, invoice_type: Optional[str] = None,
                search: Optional[str] = None, customer_id: Optional[str] = None):
        query = db.query(Invoice).filter(Invoice.company_id == company_id)
        if status:
            query = query.filter(Invoice.status == status)
        if invoice_type:
            query = query.filter(Invoice.invoice_type == invoice_type)
        if search:
            query = query.filter(Invoice.invoice_number.ilike(f"%{search}%"))
        if customer_id:
            query = query.filter(Invoice.customer_id == uuid.UUID(customer_id))

        total = query.count()
        items = (query.options(joinedload(Invoice.customer), joinedload(Invoice.vendor), joinedload(Invoice.items))
                 .order_by(Invoice.created_at.desc())
                 .offset((page - 1) * page_size).limit(page_size).all())

        for inv in items:
            if inv.customer:
                inv.customer_name = inv.customer.name
            if inv.vendor:
                inv.vendor_name = inv.vendor.name

        return items, total

    def get_by_id(self, db: Session, company_id: uuid.UUID, invoice_id: str) -> Invoice:
        invoice = (db.query(Invoice)
                   .options(joinedload(Invoice.items).joinedload(InvoiceItem.product),
                            joinedload(Invoice.customer), joinedload(Invoice.vendor))
                   .filter(Invoice.id == uuid.UUID(invoice_id), Invoice.company_id == company_id)
                   .first())
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return invoice

    def create(self, db: Session, company_id: uuid.UUID, user_id: uuid.UUID, data: InvoiceCreate) -> Invoice:
        items, subtotal, tax_total, discount_total = self._compute_items(db, data.items, company_id)
        total = subtotal - discount_total + tax_total

        invoice = Invoice(
            company_id=company_id,
            created_by=user_id,
            customer_id=uuid.UUID(data.customer_id) if data.customer_id else None,
            vendor_id=uuid.UUID(data.vendor_id) if data.vendor_id else None,
            invoice_number=data.invoice_number,
            invoice_type=InvoiceType(data.invoice_type),
            invoice_date=data.invoice_date,
            due_date=data.due_date,
            currency=data.currency,
            notes=data.notes,
            terms=data.terms,
            subtotal=subtotal,
            tax_amount=tax_total,
            discount_amount=discount_total,
            total_amount=total,
            status=InvoiceStatus.DRAFT,
        )
        for item in items:
            invoice.items.append(item)

        db.add(invoice)
        db.commit()
        db.refresh(invoice)
        return invoice

    def submit_for_approval(self, db: Session, company_id: uuid.UUID, user_id: uuid.UUID, invoice_id: str) -> Invoice:
        invoice = self.get_by_id(db, company_id, invoice_id)
        if invoice.status != InvoiceStatus.DRAFT:
            raise HTTPException(status_code=400, detail="Only draft invoices can be submitted for approval")

        invoice.status = InvoiceStatus.PENDING_APPROVAL

        approval = Approval(
            company_id=company_id,
            requested_by=user_id,
            entity_type=ApprovalEntityType.INVOICE,
            invoice_id=invoice.id,
            status=ApprovalStatus.PENDING,
        )
        db.add(approval)
        db.commit()
        db.refresh(invoice)
        return invoice

    def approve(self, db: Session, company_id: uuid.UUID, approver_id: uuid.UUID, invoice_id: str) -> Invoice:
        invoice = self.get_by_id(db, company_id, invoice_id)
        if invoice.status != InvoiceStatus.PENDING_APPROVAL:
            raise HTTPException(status_code=400, detail="Invoice is not pending approval")

        invoice.status = InvoiceStatus.APPROVED
        invoice.approved_by = approver_id
        invoice.approved_at = datetime.now(timezone.utc)

        approval = db.query(Approval).filter(Approval.invoice_id == invoice.id, Approval.status == ApprovalStatus.PENDING).first()
        if approval:
            approval.status = ApprovalStatus.APPROVED
            approval.reviewed_by = approver_id
            approval.reviewed_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(invoice)
        return invoice


invoice_service = InvoiceService()
