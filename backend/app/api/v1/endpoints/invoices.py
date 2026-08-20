from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.invoice import InvoiceType
from app.services.invoice_service import invoice_service
from app.services.tally_write_service import queue_tally_write
from app.schemas.invoice import InvoiceCreate, InvoiceUpdate
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from typing import Optional
import math
import uuid

router = APIRouter(prefix="/invoices", tags=["invoices"])


def _serialize(inv) -> dict:
    d = {
        "id": str(inv.id), "company_id": str(inv.company_id),
        "customer_id": str(inv.customer_id) if inv.customer_id else None,
        "vendor_id": str(inv.vendor_id) if inv.vendor_id else None,
        "invoice_number": inv.invoice_number, "invoice_type": inv.invoice_type.value,
        "status": inv.status.value,
        "invoice_date": inv.invoice_date.isoformat(),
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "subtotal": float(inv.subtotal), "tax_amount": float(inv.tax_amount),
        "discount_amount": float(inv.discount_amount), "total_amount": float(inv.total_amount),
        "paid_amount": float(inv.paid_amount), "currency": inv.currency,
        "notes": inv.notes, "created_at": inv.created_at.isoformat(),
        "customer_name": getattr(inv, "customer_name", None) or (inv.customer.name if inv.customer else None),
        "vendor_name": getattr(inv, "vendor_name", None) or (inv.vendor.name if inv.vendor else None),
        "items": [],
    }
    if hasattr(inv, "items") and inv.items:
        d["items"] = [
            {
                "id": str(item.id), "description": item.description,
                "quantity": float(item.quantity), "unit_price": float(item.unit_price),
                "tax_rate": float(item.tax_rate), "tax_amount": float(item.tax_amount),
                "discount_rate": float(item.discount_rate), "line_total": float(item.line_total),
                "product_id": str(item.product_id) if item.product_id else None,
            }
            for item in inv.items
        ]
    return d


@router.get("")
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    invoice_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = invoice_service.get_all(
        db, current_user.company_id, page, page_size, status, invoice_type, search, customer_id
    )
    return {
        "items": [_serialize(inv) for inv in items],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.get("/{invoice_id}")
def get_invoice(
    invoice_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    inv = invoice_service.get_by_id(db, current_user.company_id, invoice_id)
    return _serialize(inv)


@router.post("")
def create_invoice(
    data: InvoiceCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    inv = invoice_service.create(db, current_user.company_id, current_user.id, data)
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.CREATE,
                      entity_type="invoice", entity_id=inv.id,
                      description=f"Invoice {inv.invoice_number} created")
    try:
        tally_date = inv.invoice_date.strftime("%Y%m%d")
        amount_str = str(int(float(inv.total_amount)))
        if inv.invoice_type == InvoiceType.SALES:
            customer_name = ""
            if inv.customer_id:
                cust = db.query(Customer).filter(Customer.id == inv.customer_id).first()
                customer_name = cust.name if cust else ""
            tally_queued = queue_tally_write(
                db, current_user.company_id, "CREATE_SALES_VOUCHER",
                {
                    "date": tally_date,
                    "party_ledger": customer_name,
                    "sales_ledger": "Sales",
                    "amount": amount_str,
                    "narration": inv.invoice_number,
                },
            )
        else:
            vendor_name = ""
            if inv.vendor_id:
                vend = db.query(Vendor).filter(Vendor.id == inv.vendor_id).first()
                vendor_name = vend.name if vend else ""
            tally_queued = queue_tally_write(
                db, current_user.company_id, "CREATE_PURCHASE_VOUCHER",
                {
                    "date": tally_date,
                    "party_ledger": vendor_name,
                    "purchase_ledger": "Purchases",
                    "amount": amount_str,
                    "narration": inv.invoice_number,
                },
            )
        if tally_queued:
            db.commit()
    except Exception:
        pass
    return _serialize(inv)


