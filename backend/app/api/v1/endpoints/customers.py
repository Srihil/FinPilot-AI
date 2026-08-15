from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.services.customer_service import customer_service
from app.services.tally_write_service import queue_tally_write
from app.schemas.customer import CustomerCreate, CustomerUpdate
from typing import Optional
import math

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("")
def list_customers(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = customer_service.get_all(db, current_user.company_id, search, page, page_size)
    return {
        "items": [
            {
                "id": str(c.id),
                "company_id": str(c.company_id),
                "name": c.name,
                "email": c.email,
                "phone": c.phone,
                "address": c.address,
                "city": c.city,
                "state": c.state,
                "country": c.country,
                "gst_number": c.gst_number,
                "pan_number": c.pan_number,
                "credit_limit": float(c.credit_limit or 0),
                "payment_terms_days": c.payment_terms_days,
                "is_active": c.is_active,
                "notes": c.notes,
                "created_at": c.created_at.isoformat(),
                "total_revenue": getattr(c, "total_revenue", 0),
                "outstanding_balance": getattr(c, "outstanding_balance", 0),
            }
            for c in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.get("/{customer_id}")
def get_customer(
    customer_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = customer_service.get_by_id(db, current_user.company_id, customer_id)
    return {"id": str(c.id), "name": c.name, "email": c.email, "phone": c.phone,
            "address": c.address, "city": c.city, "state": c.state, "country": c.country,
            "gst_number": c.gst_number, "pan_number": c.pan_number,
            "credit_limit": float(c.credit_limit or 0), "payment_terms_days": c.payment_terms_days,
            "is_active": c.is_active, "notes": c.notes, "created_at": c.created_at.isoformat(),
            "company_id": str(c.company_id)}


@router.post("")
def create_customer(
    data: CustomerCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    c = customer_service.create(db, current_user.company_id, data)
    try:
        tally_queued = queue_tally_write(
            db, current_user.company_id, "CREATE_LEDGER",
            {"name": c.name, "group": "Sundry Debtors", "opening_balance": "0"},
        )
        if tally_queued:
            db.commit()
    except Exception:
        pass
    return {"id": str(c.id), "name": c.name, "message": "Customer created successfully"}


@router.put("/{customer_id}")
def update_customer(
    customer_id: str,
    data: CustomerUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    c = customer_service.update(db, current_user.company_id, customer_id, data)
    return {"id": str(c.id), "name": c.name, "message": "Customer updated successfully"}


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    customer_service.delete(db, current_user.company_id, customer_id)
    return {"message": "Customer deactivated successfully"}
