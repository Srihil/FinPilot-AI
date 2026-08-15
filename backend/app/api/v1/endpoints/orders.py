"""
Orders endpoints — Sales Orders and Purchase Orders.

Note: TallyPrime does not have a native Sales Order / Purchase Order API via the
standard XML/TDL interface used by this connector. These orders are stored locally
in FinPilot only (tally_sync_status = "local_only").
If your TallyPrime version and TDL support order sync, this can be extended later.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.db.base import get_db
from app.models.audit_log import AuditAction
from app.models.order import Order, OrderItem
from app.models.user import User
from app.services.audit_service import audit_service

router = APIRouter(prefix="/orders", tags=["orders"])


def _auto_order_number(order_type: str) -> str:
    prefix = "SO" if order_type == "SALES" else "PO"
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


class OrderItemCreate(BaseModel):
    stock_item_name: Optional[str] = None
    description: Optional[str] = None
    quantity: float = 1
    unit: Optional[str] = None
    unit_price: float = 0


class OrderCreate(BaseModel):
    order_type: str  # SALES | PURCHASE
    party_name: Optional[str] = None
    party_ledger: Optional[str] = None
    order_date: Optional[str] = None
    due_date: Optional[str] = None
    narration: Optional[str] = None
    items: List[OrderItemCreate] = []


class OrderUpdate(BaseModel):
    party_name: Optional[str] = None
    party_ledger: Optional[str] = None
    order_date: Optional[str] = None
    due_date: Optional[str] = None
    narration: Optional[str] = None
    status: Optional[str] = None


def _serialize_order(o: Order) -> dict:
    return {
        "id": str(o.id),
        "order_number": o.order_number,
        "order_type": o.order_type,
        "party_name": o.party_name,
        "party_ledger": o.party_ledger,
        "order_date": o.order_date.isoformat() if o.order_date else None,
        "due_date": o.due_date.isoformat() if o.due_date else None,
        "total_amount": float(o.total_amount or 0),
        "narration": o.narration,
        "status": o.status,
        "tally_sync_status": o.tally_sync_status,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "items": [
            {
                "id": str(i.id),
                "stock_item_name": i.stock_item_name,
                "description": i.description,
                "quantity": float(i.quantity or 1),
                "unit": i.unit,
                "unit_price": float(i.unit_price or 0),
                "amount": float(i.amount or 0),
            }
            for i in (o.items or [])
        ],
    }


@router.get("")
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    order_type: Optional[str] = Query(None, description="SALES or PURCHASE"),
    status: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(Order).filter(
        Order.company_id == current_user.company_id,
        Order.is_active == True,
    )
    if order_type:
        q = q.filter(Order.order_type == order_type.upper())
    if status:
        q = q.filter(Order.status == status.upper())
    if search:
        q = q.filter(Order.party_name.ilike(f"%{search}%") | Order.order_number.ilike(f"%{search}%"))
    total = q.count()
    orders = q.order_by(Order.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_serialize_order(o) for o in orders],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("")
def create_order(
    data: OrderCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    order_type = data.order_type.upper()
    if order_type not in ("SALES", "PURCHASE"):
        raise HTTPException(status_code=422, detail="order_type must be SALES or PURCHASE")

    order_date = None
    if data.order_date:
        try:
            order_date = datetime.fromisoformat(data.order_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid order_date format (use YYYY-MM-DD)")

    due_date = None
    if data.due_date:
        try:
            due_date = datetime.fromisoformat(data.due_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid due_date format (use YYYY-MM-DD)")

    # Build items and calculate total
    items = []
    total = 0.0
    for item_data in data.items:
        amount = float(item_data.quantity) * float(item_data.unit_price)
        total += amount
        items.append(OrderItem(
            stock_item_name=item_data.stock_item_name,
            description=item_data.description,
            quantity=item_data.quantity,
            unit=item_data.unit,
            unit_price=item_data.unit_price,
            amount=amount,
        ))

    order = Order(
        company_id=current_user.company_id,
        created_by=current_user.id,
        order_number=_auto_order_number(order_type),
        order_type=order_type,
        party_name=data.party_name,
        party_ledger=data.party_ledger,
        order_date=order_date or datetime.now(timezone.utc),
        due_date=due_date,
        total_amount=total,
        narration=data.narration,
        status="DRAFT",
        tally_sync_status="local_only",
        items=items,
    )
    db.add(order)
    db.commit()
    db.refresh(order)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE,
        entity_type="order",
        entity_id=order.id,
        description=f"Created {order_type} order: {order.order_number}",
    )
    return _serialize_order(order)


@router.get("/{order_id}")
def get_order(
    order_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == uuid.UUID(order_id),
        Order.company_id == current_user.company_id,
        Order.is_active == True,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return _serialize_order(order)


@router.patch("/{order_id}")
def update_order(
    order_id: str,
    data: OrderUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == uuid.UUID(order_id),
        Order.company_id == current_user.company_id,
        Order.is_active == True,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if data.party_name is not None:
        order.party_name = data.party_name
    if data.party_ledger is not None:
        order.party_ledger = data.party_ledger
    if data.narration is not None:
        order.narration = data.narration
    if data.status is not None:
        valid_statuses = {"DRAFT", "CONFIRMED", "FULFILLED", "CANCELLED"}
        if data.status.upper() not in valid_statuses:
            raise HTTPException(status_code=422, detail=f"status must be one of {valid_statuses}")
        order.status = data.status.upper()
    if data.order_date is not None:
        try:
            order.order_date = datetime.fromisoformat(data.order_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid order_date")
    if data.due_date is not None:
        try:
            order.due_date = datetime.fromisoformat(data.due_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid due_date")

    order.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="order", entity_id=order.id,
                      description=f"Updated order: {order.order_number}")
    return _serialize_order(order)


@router.delete("/{order_id}")
def delete_order(
    order_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(
        Order.id == uuid.UUID(order_id),
        Order.company_id == current_user.company_id,
        Order.is_active == True,
    ).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order.is_active = False
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                      entity_type="order", entity_id=order.id,
                      description=f"Deleted order: {order.order_number}")
    return {"deleted": True, "message": f"Order {order.order_number} deleted."}
