from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.models.expense import Expense, ExpenseStatus
from app.models.vendor import Vendor
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from app.services.tally_write_service import queue_tally_write
from datetime import datetime, timezone
from typing import Optional
import math
import uuid

router = APIRouter(prefix="/expenses", tags=["expenses"])


def _serialize(e) -> dict:
    return {
        "id": str(e.id), "company_id": str(e.company_id),
        "vendor_id": str(e.vendor_id) if e.vendor_id else None,
        "title": e.title, "description": e.description, "category": e.category,
        "expense_date": e.expense_date.isoformat(),
        "amount": float(e.amount), "tax_amount": float(e.tax_amount),
        "total_amount": float(e.total_amount), "currency": e.currency,
        "status": e.status.value, "reference_number": e.reference_number,
        "notes": e.notes, "created_at": e.created_at.isoformat(),
        "vendor_name": e.vendor.name if e.vendor else None,
    }


# These categories are accounting vouchers, not operational expenses.
# They appear in the Vouchers page under their own tabs, not here.
_VOUCHER_CATEGORIES = {
    "Receipt", "Payment", "Journal", "Contra",
    "Credit Note", "Debit Note", "Purchase", "Purchase Return",
}


@router.get("")
def list_expenses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    vendor_id: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Expense).options(joinedload(Expense.vendor)).filter(
        Expense.company_id == current_user.company_id,
        ~Expense.category.in_(_VOUCHER_CATEGORIES),
    )
    if status:
        query = query.filter(Expense.status == status)
    if category:
        query = query.filter(Expense.category == category)
    if vendor_id:
        query = query.filter(Expense.vendor_id == uuid.UUID(vendor_id))

    total = query.count()
    items = query.order_by(Expense.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [_serialize(e) for e in items],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.post("")
def create_expense(
    data: ExpenseCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    e = Expense(
        company_id=current_user.company_id,
        created_by=current_user.id,
        vendor_id=uuid.UUID(data.vendor_id) if data.vendor_id else None,
        title=data.title, description=data.description, category=data.category,
        expense_date=data.expense_date, amount=data.amount, tax_amount=data.tax_amount,
        total_amount=data.amount + data.tax_amount, currency=data.currency,
        reference_number=data.reference_number, notes=data.notes,
        status=ExpenseStatus.DRAFT,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.CREATE,
                      entity_type="expense", entity_id=e.id,
                      description=f"Expense '{e.title}' created for ₹{float(e.total_amount):,.0f}")
    try:
        vendor_name = "Cash"
        if e.vendor_id:
            vend = db.query(Vendor).filter(Vendor.id == e.vendor_id).first()
            if vend:
                vendor_name = vend.name
        tally_queued = queue_tally_write(
            db, current_user.company_id, "CREATE_PURCHASE_VOUCHER",
            {
                "date": e.expense_date.strftime("%Y%m%d"),
                "party_ledger": vendor_name,
                "purchase_ledger": "Purchases",
                "amount": str(int(float(e.total_amount))),
                "narration": e.title,
            },
        )
        if tally_queued:
            db.commit()
    except Exception:
        pass
    return _serialize(e)


