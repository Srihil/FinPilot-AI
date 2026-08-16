"""
Inventory endpoints — Stock Categories and Stock Transactions.

Stock Categories: Synced to TallyPrime via the standard connector.
Stock Transactions: local inventory movement records (Stock Journal, Physical Stock, etc.)
  - Tally sync requires TDL voucher handlers not included in the standard connector.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.db.base import get_db
from app.models.audit_log import AuditAction
from app.models.stock_category import StockCategory
from app.models.stock_transaction import StockTransaction
from app.models.tally_connector import TallyConnector, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, JobStatus, TallyJobOperation
from app.models.user import User
from app.services.audit_service import audit_service

router = APIRouter(prefix="/inventory", tags=["inventory"])

TRANSACTION_TYPES = {
    "STOCK_JOURNAL", "PHYSICAL_STOCK",
    "DELIVERY_NOTE", "RECEIPT_NOTE",
    "REJECTION_IN", "REJECTION_OUT",
}

TRANSACTION_TYPE_LABELS = {
    "STOCK_JOURNAL": "Stock Journal",
    "PHYSICAL_STOCK": "Physical Stock",
    "DELIVERY_NOTE": "Delivery Note",
    "RECEIPT_NOTE": "Receipt Note",
    "REJECTION_IN": "Rejections In",
    "REJECTION_OUT": "Rejections Out",
}


# ─── Stock Categories ────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str
    parent: Optional[str] = None
    description: Optional[str] = None


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    parent: Optional[str] = None
    description: Optional[str] = None


def _tally_cat_key(company_id: uuid.UUID, name: str) -> str:
    return f"{company_id}::{name.strip().lower()}"


def _serialize_category(c: StockCategory) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "parent": c.parent,
        "description": c.description,
        "is_active": c.is_active,
        "source": getattr(c, "source", "finpilot"),
        "tally_sync_status": getattr(c, "tally_sync_status", "pending"),
        "synced_at": c.synced_at.isoformat() if getattr(c, "synced_at", None) else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@router.get("/stock-categories")
def list_stock_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(StockCategory).filter(
        StockCategory.company_id == current_user.company_id,
        StockCategory.is_active == True,
    )
    if search:
        q = q.filter(StockCategory.name.ilike(f"%{search}%"))
    total = q.count()
    items = q.order_by(StockCategory.name).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_serialize_category(c) for c in items],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("/stock-categories")
def create_stock_category(
    data: CategoryCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Category name is required")
    tkey = _tally_cat_key(current_user.company_id, name)
    existing = db.query(StockCategory).filter(
        StockCategory.company_id == current_user.company_id,
        StockCategory.tally_key == tkey,
        StockCategory.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Category '{name}' already exists")
    cat = StockCategory(
        company_id=current_user.company_id,
        name=name,
        parent=data.parent or None,
        description=data.description or None,
        tally_key=tkey,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(cat)
    db.flush()

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    if connector:
        payload = {"name": name}
        raw_parent = (data.parent or "").strip()
        if raw_parent and raw_parent.lower() not in ("", "primary"):
            payload["parent"] = raw_parent
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_STOCK_CATEGORY,
            payload=payload,
            idempotency_key=f"create_stock_category::{cat.id}",
        )
        db.add(job)
        db.flush()
        cat.tally_job_id = job.id

    db.commit()
    db.refresh(cat)
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.CREATE,
                      entity_type="stock_category", entity_id=cat.id,
                      description=f"Created stock category: {name}")
    return _serialize_category(cat)


@router.patch("/stock-categories/{cat_id}")
def update_stock_category(
    cat_id: str,
    data: CategoryUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    cat = db.query(StockCategory).filter(
        StockCategory.id == uuid.UUID(cat_id),
        StockCategory.company_id == current_user.company_id,
        StockCategory.is_active == True,
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Stock category not found")
    if data.name is not None:
        cat.name = data.name.strip()
    if data.parent is not None:
        cat.parent = data.parent.strip() or None
    if data.description is not None:
        cat.description = data.description
    cat.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="stock_category", entity_id=cat.id,
                      description=f"Updated stock category: {cat.name}")
    return _serialize_category(cat)


@router.delete("/stock-categories/{cat_id}")
def delete_stock_category(
    cat_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    cat = db.query(StockCategory).filter(
        StockCategory.id == uuid.UUID(cat_id),
        StockCategory.company_id == current_user.company_id,
        StockCategory.is_active == True,
    ).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Stock category not found")

    # Cancel any in-flight create job
    if getattr(cat, "tally_job_id", None):
        pending_job = db.query(TallyIntegrationJob).filter(
            TallyIntegrationJob.id == cat.tally_job_id,
            TallyIntegrationJob.status == JobStatus.PENDING,
        ).first()
        if pending_job:
            pending_job.status = JobStatus.CANCELLED

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    sync_status = getattr(cat, "tally_sync_status", "pending")
    if connector and sync_status in ("synced", "finpilot", "delete_failed"):
        cat.tally_sync_status = "delete_pending"
        db.flush()
        import secrets as _secrets
        ikey = f"delete::DELETE_STOCK_CATEGORY::{current_user.company_id}::{cat.name.strip().lower()}::{_secrets.token_hex(4)}"
        db.add(TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            operation=TallyJobOperation.DELETE_STOCK_CATEGORY,
            payload={"name": cat.name},
            idempotency_key=ikey,
        ))
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="stock_category", entity_id=cat.id,
                          description=f"Delete queued for stock category: {cat.name}")
        return {"status": "pending", "message": "Delete queued. The category will be removed once TallyPrime confirms."}
    else:
        cat.is_active = False
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="stock_category", entity_id=cat.id,
                          description=f"Deleted stock category: {cat.name}")
        return {"status": "deleted", "message": "Deleted successfully."}


# ─── Stock Transactions ──────────────────────────────────────────────────────

class StockEntryItem(BaseModel):
    stock_item_name: str
    quantity: float
    unit: Optional[str] = None
    rate: Optional[float] = None
    godown: Optional[str] = None


class StockTransactionCreate(BaseModel):
    transaction_type: str
    transaction_date: Optional[str] = None
    narration: Optional[str] = None
    party_name: Optional[str] = None
    from_godown: Optional[str] = None
    to_godown: Optional[str] = None
    entries: List[StockEntryItem] = []


def _auto_txn_number(txn_type: str) -> str:
    prefixes = {
        "STOCK_JOURNAL": "SJ",
        "PHYSICAL_STOCK": "PS",
        "DELIVERY_NOTE": "DN",
        "RECEIPT_NOTE": "RN",
        "REJECTION_IN": "RI",
        "REJECTION_OUT": "RO",
    }
    prefix = prefixes.get(txn_type, "ST")
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _serialize_txn(t: StockTransaction) -> dict:
    return {
        "id": str(t.id),
        "transaction_number": t.transaction_number,
        "transaction_type": t.transaction_type,
        "transaction_type_label": TRANSACTION_TYPE_LABELS.get(t.transaction_type, t.transaction_type),
        "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
        "narration": t.narration,
        "party_name": t.party_name,
        "from_godown": t.from_godown,
        "to_godown": t.to_godown,
        "entries": t.entries or [],
        "tally_sync_status": t.tally_sync_status,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/stock-transactions")
def list_stock_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    transaction_type: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(StockTransaction).filter(
        StockTransaction.company_id == current_user.company_id,
        StockTransaction.is_active == True,
    )
    if transaction_type:
        q = q.filter(StockTransaction.transaction_type == transaction_type.upper())
    if search:
        q = q.filter(
            or_(
                StockTransaction.transaction_number.ilike(f"%{search}%"),
                StockTransaction.party_name.ilike(f"%{search}%"),
                StockTransaction.narration.ilike(f"%{search}%"),
            )
        )
    if date_from:
        try:
            q = q.filter(StockTransaction.transaction_date >= datetime.fromisoformat(date_from))
        except ValueError:
            pass
    if date_to:
        try:
            q = q.filter(StockTransaction.transaction_date <= datetime.fromisoformat(date_to))
        except ValueError:
            pass
    total = q.count()
    items = q.order_by(StockTransaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": [_serialize_txn(t) for t in items],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "tally_note": "Stock transactions are local-only. TallyPrime sync requires TDL voucher configuration.",
        "transaction_types": [
            {"value": k, "label": v} for k, v in TRANSACTION_TYPE_LABELS.items()
        ],
    }


@router.post("/stock-transactions")
def create_stock_transaction(
    data: StockTransactionCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    txn_type = data.transaction_type.upper()
    if txn_type not in TRANSACTION_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"transaction_type must be one of: {', '.join(sorted(TRANSACTION_TYPES))}"
        )
    txn_date = None
    if data.transaction_date:
        try:
            txn_date = datetime.fromisoformat(data.transaction_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid transaction_date (use YYYY-MM-DD)")

    entries_data = [e.model_dump() for e in data.entries]

    txn = StockTransaction(
        company_id=current_user.company_id,
        created_by=current_user.id,
        transaction_number=_auto_txn_number(txn_type),
        transaction_type=txn_type,
        transaction_date=txn_date or datetime.now(timezone.utc),
        narration=data.narration or None,
        party_name=data.party_name or None,
        from_godown=data.from_godown or None,
        to_godown=data.to_godown or None,
        entries=entries_data,
        tally_sync_status="local_only",
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.CREATE,
                      entity_type="stock_transaction", entity_id=txn.id,
                      description=f"Created {txn_type}: {txn.transaction_number}")
    return _serialize_txn(txn)


@router.delete("/stock-transactions/{txn_id}")
def delete_stock_transaction(
    txn_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    txn = db.query(StockTransaction).filter(
        StockTransaction.id == uuid.UUID(txn_id),
        StockTransaction.company_id == current_user.company_id,
        StockTransaction.is_active == True,
    ).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Stock transaction not found")
    txn.is_active = False
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                      entity_type="stock_transaction", entity_id=txn.id,
                      description=f"Deleted transaction: {txn.transaction_number}")
    return {"deleted": True}
