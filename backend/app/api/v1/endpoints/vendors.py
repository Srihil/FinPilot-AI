from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.services.vendor_service import vendor_service
from app.services.tally_write_service import queue_tally_write
from app.schemas.vendor import VendorCreate, VendorUpdate
from typing import Optional
import math

router = APIRouter(prefix="/vendors", tags=["vendors"])


@router.get("")
def list_vendors(
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = vendor_service.get_all(db, current_user.company_id, search, page, page_size)
    return {
        "items": [
            {
                "id": str(v.id), "company_id": str(v.company_id), "name": v.name,
                "email": v.email, "phone": v.phone, "address": v.address,
                "city": v.city, "state": v.state, "country": v.country,
                "gst_number": v.gst_number, "pan_number": v.pan_number,
                "payment_terms_days": v.payment_terms_days, "is_active": v.is_active,
                "notes": v.notes, "created_at": v.created_at.isoformat(),
                "total_purchases": getattr(v, "total_purchases", 0),
                "outstanding_payable": getattr(v, "outstanding_payable", 0),
            }
            for v in items
        ],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }


@router.post("")
def create_vendor(
    data: VendorCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    v = vendor_service.create(db, current_user.company_id, data)
    try:
        tally_queued = queue_tally_write(
            db, current_user.company_id, "CREATE_LEDGER",
            {"name": v.name, "group": "Sundry Creditors", "opening_balance": "0"},
        )
        if tally_queued:
            db.commit()
    except Exception:
        pass
    return {"id": str(v.id), "name": v.name, "message": "Vendor created successfully"}


@router.put("/{vendor_id}")
def update_vendor(
    vendor_id: str,
    data: VendorUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    v = vendor_service.update(db, current_user.company_id, vendor_id, data)
    return {"id": str(v.id), "name": v.name, "message": "Vendor updated successfully"}


@router.delete("/{vendor_id}")
def delete_vendor(
    vendor_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    import uuid as _uuid
    from app.models.vendor import Vendor
    vendor = db.query(Vendor).filter(
        Vendor.id == _uuid.UUID(vendor_id),
        Vendor.company_id == current_user.company_id,
    ).first()

    vendor_service.delete(db, current_user.company_id, vendor_id)

    tally_queued = False
    if vendor:
        tally_queued = queue_tally_write(
            db, current_user.company_id, "DELETE_LEDGER", {"name": vendor.name}
        )
        if tally_queued:
            db.commit()

    msg = "Vendor deleted from FinPilot and delete queued for TallyPrime." if tally_queued else "Vendor deleted from FinPilot."
    return {"message": msg, "tally_queued": tally_queued}
