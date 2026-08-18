"""
Management endpoints — unified overview, Tally master management, and voucher management.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import get_current_user, require_admin_or_accountant, require_admin
from app.db.base import get_db
from app.models.audit_log import AuditAction
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.approval import Approval
from app.models.invoice import Invoice, InvoiceType
from app.models.payment import Payment
from app.models.product import Product
from app.models.tally_connector import TallyConnector, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, JobStatus, TallyJobOperation
from app.models.tally_masters import TallyGodown, TallyGroup, TallyLedger, TallyStockGroup, TallyStockItem, TallyUnit, TallyVoucherType
from app.models.user import User
from app.models.vendor import Vendor
from app.services.audit_service import audit_service

router = APIRouter(prefix="/management", tags=["management"])

# ─── helpers ────────────────────────────────────────────────────────────────────

_HEARTBEAT_TIMEOUT = 90  # seconds


def _connector_online(c: TallyConnector) -> bool:
    if not c.last_heartbeat:
        return False
    return (datetime.now(timezone.utc) - c.last_heartbeat).total_seconds() < _HEARTBEAT_TIMEOUT


def _tally_key(company_id: uuid.UUID, name: str) -> str:
    return f"{company_id}::{name.strip().lower()}"


def _paginate(query, page: int, page_size: int):
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


def _reconcile_sync_status(db: Session, records: list) -> bool:
    """Auto-fix 'pending' tally_sync_status when the corresponding job already completed."""
    pending_job_ids = [
        r.tally_job_id for r in records
        if getattr(r, 'tally_sync_status', None) == 'pending' and getattr(r, 'tally_job_id', None)
    ]
    if not pending_job_ids:
        return False
    jobs = {
        j.id: j for j in db.query(TallyIntegrationJob).filter(
            TallyIntegrationJob.id.in_(pending_job_ids),
            TallyIntegrationJob.status.in_([JobStatus.SUCCESS, JobStatus.FAILED]),
        ).all()
    }
    now = datetime.now(timezone.utc)
    changed = False
    for r in records:
        job = jobs.get(getattr(r, 'tally_job_id', None))
        if job:
            if job.status == JobStatus.SUCCESS:
                r.tally_sync_status = 'synced'
                r.synced_at = job.completed_at or now
                changed = True
            elif job.status == JobStatus.FAILED:
                r.tally_sync_status = 'failed'
                changed = True
    return changed


def _cancel_pending_job(db: Session, job_id) -> None:
    if not job_id:
        return
    job = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.id == job_id,
        TallyIntegrationJob.status == JobStatus.PENDING,
    ).first()
    if job:
        job.status = JobStatus.CANCELLED


def _queue_tally_delete(db: Session, company_id: uuid.UUID, operation: TallyJobOperation, name: str) -> bool:
    """Queue a Tally delete job. Returns True if queued, False if no active connector."""
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if not connector:
        return False
    import secrets as _secrets
    ikey = f"delete::{operation.value}::{company_id}::{name.strip().lower()}::{_secrets.token_hex(4)}"
    db.add(TallyIntegrationJob(
        company_id=company_id,
        connector_id=connector.id,
        operation=operation,
        payload={"name": name},
        idempotency_key=ikey,
    ))
    return True


# ─── Overview ───────────────────────────────────────────────────────────────────

@router.get("/overview")
def get_overview(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id

    total_customers = db.query(func.count(Customer.id)).filter(
        Customer.company_id == cid, Customer.is_active == True
    ).scalar() or 0

    total_vendors = db.query(func.count(Vendor.id)).filter(
        Vendor.company_id == cid, Vendor.is_active == True
    ).scalar() or 0

    total_products = db.query(func.count(Product.id)).filter(
        Product.company_id == cid, Product.is_active == True
    ).scalar() or 0

    total_ledgers = db.query(func.count(TallyLedger.id)).filter(
        TallyLedger.company_id == cid, TallyLedger.is_active == True
    ).scalar() or 0

    total_stock_groups = db.query(func.count(TallyStockGroup.id)).filter(
        TallyStockGroup.company_id == cid, TallyStockGroup.is_active == True
    ).scalar() or 0

    total_units = db.query(func.count(TallyUnit.id)).filter(
        TallyUnit.company_id == cid, TallyUnit.is_active == True
    ).scalar() or 0

    total_godowns = db.query(func.count(TallyGodown.id)).filter(
        TallyGodown.company_id == cid, TallyGodown.is_active == True
    ).scalar() or 0

    total_invoices = db.query(func.count(Invoice.id)).filter(
        Invoice.company_id == cid
    ).scalar() or 0

    total_expenses = db.query(func.count(Expense.id)).filter(
        Expense.company_id == cid
    ).scalar() or 0

    pending_jobs = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status.in_([JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RUNNING]),
    ).scalar() or 0

    failed_jobs = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.FAILED,
    ).scalar() or 0

    # Last successful sync
    last_sync_job = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.SUCCESS,
    ).order_by(TallyIntegrationJob.completed_at.desc()).first()

    last_sync = last_sync_job.completed_at.isoformat() if last_sync_job and last_sync_job.completed_at else None

    # Connector status
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == cid,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).order_by(TallyConnector.created_at.desc()).first()

    tally_connected = connector is not None
    tally_online = _connector_online(connector) if connector else False
    tally_company = connector.tally_company_name if connector else None

    return {
        "totals": {
            "customers": total_customers,
            "vendors": total_vendors,
            "products": total_products,
            "ledgers": total_ledgers,
            "stock_groups": total_stock_groups,
            "units": total_units,
            "godowns": total_godowns,
            "vouchers": total_invoices + total_expenses,
        },
        "sync": {
            "pending_jobs": pending_jobs,
            "failed_jobs": failed_jobs,
            "last_sync": last_sync,
        },
        "tally": {
            "connected": tally_connected,
            "online": tally_online,
            "company": tally_company,
            "connector_name": connector.connector_name if connector else None,
            "device": connector.device_name if connector else None,
            "last_heartbeat": connector.last_heartbeat.isoformat() if connector and connector.last_heartbeat else None,
        },
    }


# ─── Ledger management ──────────────────────────────────────────────────────────

class LedgerCreate(BaseModel):
    name: str
    parent_group: Optional[str] = "Sundry Debtors"
    opening_balance: Optional[float] = 0.0


@router.get("/ledgers")
def list_ledgers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyLedger).filter(
        TallyLedger.company_id == current_user.company_id,
        TallyLedger.is_active == True,
    )
    if search:
        q = q.filter(TallyLedger.name.ilike(f"%{search}%"))
    q = q.order_by(TallyLedger.name)
    result = _paginate(q, page, page_size)
    records = result["items"]
    if _reconcile_sync_status(db, records):
        db.commit()
    result["items"] = [
        {
            "id": str(r.id),
            "name": r.name,
            "parent_group": r.parent_group,
            "opening_balance": r.opening_balance,
            "closing_balance": r.closing_balance,
            "source": r.source,
            "tally_sync_status": r.tally_sync_status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return result


@router.post("/ledgers")
def create_ledger(
    data: LedgerCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Ledger name is required")

    key = _tally_key(current_user.company_id, name)
    existing = db.query(TallyLedger).filter(
        TallyLedger.company_id == current_user.company_id,
        TallyLedger.tally_key == key,
        TallyLedger.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Ledger '{name}' already exists")

    ledger = TallyLedger(
        company_id=current_user.company_id,
        name=name,
        parent_group=data.parent_group,
        opening_balance=data.opening_balance or 0.0,
        tally_key=key,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(ledger)
    db.flush()

    # Queue Tally job
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    tally_queued = False
    if connector:
        ikey = f"create_ledger::{ledger.id}"
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_LEDGER,
            payload={
                "name": name,
                "group": data.parent_group or "Sundry Debtors",
                "opening_balance": str(int(data.opening_balance or 0)),
            },
            idempotency_key=ikey,
        )
        db.add(job)
        db.flush()
        ledger.tally_job_id = job.id
        tally_queued = True

    db.commit()
    db.refresh(ledger)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE,
        entity_type="tally_ledger",
        entity_id=ledger.id,
        description=f"Created Tally ledger: {name}",
    )

    return {
        "id": str(ledger.id),
        "name": ledger.name,
        "parent_group": ledger.parent_group,
        "tally_sync_status": ledger.tally_sync_status,
        "tally_queued": tally_queued,
    }


class LedgerUpdate(BaseModel):
    name: Optional[str] = None
    parent_group: Optional[str] = None
    opening_balance: Optional[float] = None


@router.patch("/ledgers/{ledger_id}")
def update_ledger(
    ledger_id: str,
    data: LedgerUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    ledger = db.query(TallyLedger).filter(
        TallyLedger.id == uuid.UUID(ledger_id),
        TallyLedger.company_id == current_user.company_id,
        TallyLedger.is_active == True,
    ).first()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    was_synced = ledger.tally_sync_status == "synced"
    if data.name is not None:
        ledger.name = data.name.strip()
    if data.parent_group is not None:
        ledger.parent_group = data.parent_group
    if data.opening_balance is not None:
        ledger.opening_balance = data.opening_balance
    ledger.updated_at = datetime.now(timezone.utc)

    # If pending job, update its payload too
    if ledger.tally_job_id and not was_synced:
        job = db.query(TallyIntegrationJob).filter(
            TallyIntegrationJob.id == ledger.tally_job_id,
            TallyIntegrationJob.status == JobStatus.PENDING,
        ).first()
        if job and data.name:
            job.payload = {**(job.payload or {}), "name": ledger.name}

    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="tally_ledger", entity_id=ledger.id,
                      description=f"Updated ledger: {ledger.name}")
    return {
        "id": str(ledger.id), "name": ledger.name,
        "tally_sync_status": ledger.tally_sync_status,
        "warning": "Already synced to TallyPrime — update it there manually too." if was_synced else None,
    }


@router.delete("/ledgers/{ledger_id}")
def delete_ledger(
    ledger_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    ledger = db.query(TallyLedger).filter(
        TallyLedger.id == uuid.UUID(ledger_id),
        TallyLedger.company_id == current_user.company_id,
        TallyLedger.is_active == True,
    ).first()
    if not ledger:
        raise HTTPException(status_code=404, detail="Ledger not found")

    _cancel_pending_job(db, ledger.tally_job_id)

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    if connector and ledger.tally_sync_status in ("synced", "finpilot", "delete_failed"):
        # Has an active connector and exists in Tally — queue delete, keep visible until confirmed
        ledger.tally_sync_status = "delete_pending"
        db.flush()
        _queue_tally_delete(db, current_user.company_id, TallyJobOperation.DELETE_LEDGER, ledger.name)
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_ledger", entity_id=ledger.id,
                          description=f"Delete queued for ledger: {ledger.name}")
        return {"status": "pending", "message": "Delete queued. The ledger will be removed from FinPilot once TallyPrime confirms the deletion."}
    else:
        # No connector or never synced — safe to delete from FinPilot directly
        ledger.is_active = False
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_ledger", entity_id=ledger.id,
                          description=f"Deleted ledger: {ledger.name}")
        return {"status": "deleted", "message": "Deleted successfully."}


# ─── Stock Group management ──────────────────────────────────────────────────────

class StockGroupCreate(BaseModel):
    name: str
    parent: Optional[str] = None  # None = root (do NOT send "Primary")


@router.get("/stock-groups")
def list_stock_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyStockGroup).filter(
        TallyStockGroup.company_id == current_user.company_id,
        TallyStockGroup.is_active == True,
        TallyStockGroup.tally_sync_status != 'failed',
    )
    if search:
        q = q.filter(TallyStockGroup.name.ilike(f"%{search}%"))
    q = q.order_by(TallyStockGroup.name)
    result = _paginate(q, page, page_size)
    records = result["items"]
    if _reconcile_sync_status(db, records):
        db.commit()
    result["items"] = [
        {
            "id": str(r.id),
            "name": r.name,
            "parent": r.parent,
            "source": r.source,
            "tally_sync_status": r.tally_sync_status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return result


@router.post("/stock-groups")
def create_stock_group(
    data: StockGroupCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Stock group name is required")

    key = _tally_key(current_user.company_id, name)
    existing = db.query(TallyStockGroup).filter(
        TallyStockGroup.company_id == current_user.company_id,
        TallyStockGroup.tally_key == key,
        TallyStockGroup.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Stock group '{name}' already exists")

    sg = TallyStockGroup(
        company_id=current_user.company_id,
        name=name,
        parent=data.parent or None,
        tally_key=key,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(sg)
    db.flush()

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    tally_queued = False
    if connector:
        payload = {"name": name}
        # Only include parent if it's a real parent (not "Primary")
        if data.parent and data.parent.strip().lower() not in ("", "primary"):
            payload["parent"] = data.parent.strip()
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_STOCK_GROUP,
            payload=payload,
            idempotency_key=f"create_stock_group::{sg.id}",
        )
        db.add(job)
        db.flush()
        sg.tally_job_id = job.id
        tally_queued = True

    db.commit()
    db.refresh(sg)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE,
        entity_type="tally_stock_group",
        entity_id=sg.id,
        description=f"Created Tally stock group: {name}",
    )

    return {
        "id": str(sg.id),
        "name": sg.name,
        "parent": sg.parent,
        "tally_sync_status": sg.tally_sync_status,
        "tally_queued": tally_queued,
    }


class StockGroupUpdate(BaseModel):
    name: Optional[str] = None
    parent: Optional[str] = None


@router.patch("/stock-groups/{sg_id}")
def update_stock_group(
    sg_id: str,
    data: StockGroupUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    sg = db.query(TallyStockGroup).filter(
        TallyStockGroup.id == uuid.UUID(sg_id),
        TallyStockGroup.company_id == current_user.company_id,
        TallyStockGroup.is_active == True,
    ).first()
    if not sg:
        raise HTTPException(status_code=404, detail="Stock group not found")
    was_synced = sg.tally_sync_status == "synced"
    if data.name is not None:
        sg.name = data.name.strip()
    if data.parent is not None:
        sg.parent = data.parent.strip() or None
    sg.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="tally_stock_group", entity_id=sg.id,
                      description=f"Updated stock group: {sg.name}")
    return {
        "id": str(sg.id), "name": sg.name, "tally_sync_status": sg.tally_sync_status,
        "warning": "Already synced to TallyPrime — update it there manually too." if was_synced else None,
    }


@router.delete("/stock-groups/{sg_id}")
def delete_stock_group(
    sg_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    sg = db.query(TallyStockGroup).filter(
        TallyStockGroup.id == uuid.UUID(sg_id),
        TallyStockGroup.company_id == current_user.company_id,
        TallyStockGroup.is_active == True,
    ).first()
    if not sg:
        raise HTTPException(status_code=404, detail="Stock group not found")
    _cancel_pending_job(db, sg.tally_job_id)
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if connector and sg.tally_sync_status in ("synced", "finpilot", "delete_failed"):
        sg.tally_sync_status = "delete_pending"
        db.flush()
        _queue_tally_delete(db, current_user.company_id, TallyJobOperation.DELETE_STOCK_GROUP, sg.name)
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_stock_group", entity_id=sg.id,
                          description=f"Delete queued for stock group: {sg.name}")
        return {"status": "pending", "message": "Delete queued. The stock group will be removed from FinPilot once TallyPrime confirms the deletion."}
    else:
        sg.is_active = False
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_stock_group", entity_id=sg.id,
                          description=f"Deleted stock group: {sg.name}")
        return {"status": "deleted", "message": "Deleted successfully."}


# ─── Unit management ─────────────────────────────────────────────────────────────

class UnitCreate(BaseModel):
    name: str
    symbol: Optional[str] = None
    decimal_places: Optional[int] = 0

    @validator("symbol")
    def validate_symbol(cls, v):
        if v is not None:
            v = v.strip()
            if " " in v:
                raise ValueError("Symbol must not contain spaces")
            if len(v) > 8:
                raise ValueError("Symbol must be 8 characters or fewer")
        return v


@router.get("/units")
def list_units(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyUnit).filter(
        TallyUnit.company_id == current_user.company_id,
        TallyUnit.is_active == True,
    )
    if search:
        q = q.filter(
            or_(TallyUnit.name.ilike(f"%{search}%"), TallyUnit.symbol.ilike(f"%{search}%"))
        )
    q = q.order_by(TallyUnit.name)
    result = _paginate(q, page, page_size)
    records = result["items"]
    if _reconcile_sync_status(db, records):
        db.commit()
    result["items"] = [
        {
            "id": str(r.id),
            "name": r.name,
            "symbol": r.symbol,
            "decimal_places": r.decimal_places,
            "unit_type": r.unit_type,
            "source": r.source,
            "tally_sync_status": r.tally_sync_status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return result


@router.post("/units")
def create_unit(
    data: UnitCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Unit name is required")

    key = _tally_key(current_user.company_id, name)
    existing = db.query(TallyUnit).filter(
        TallyUnit.company_id == current_user.company_id,
        TallyUnit.tally_key == key,
        TallyUnit.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Unit '{name}' already exists")

    symbol = (data.symbol or name).strip()

    unit = TallyUnit(
        company_id=current_user.company_id,
        name=name,
        symbol=symbol,
        decimal_places=data.decimal_places or 0,
        unit_type="simple",
        tally_key=key,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(unit)
    db.flush()

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    tally_queued = False
    if connector:
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_UNIT,
            payload={
                "name": name,
                "symbol": symbol,
                "decimal_places": str(data.decimal_places or 0),
            },
            idempotency_key=f"create_unit::{unit.id}",
        )
        db.add(job)
        db.flush()
        unit.tally_job_id = job.id
        tally_queued = True

    db.commit()
    db.refresh(unit)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE,
        entity_type="tally_unit",
        entity_id=unit.id,
        description=f"Created Tally unit: {name} ({symbol})",
    )

    return {
        "id": str(unit.id),
        "name": unit.name,
        "symbol": unit.symbol,
        "decimal_places": unit.decimal_places,
        "tally_sync_status": unit.tally_sync_status,
        "tally_queued": tally_queued,
    }


class UnitUpdate(BaseModel):
    name: Optional[str] = None
    symbol: Optional[str] = None
    decimal_places: Optional[int] = None


@router.patch("/units/{unit_id}")
def update_unit(
    unit_id: str,
    data: UnitUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    unit = db.query(TallyUnit).filter(
        TallyUnit.id == uuid.UUID(unit_id),
        TallyUnit.company_id == current_user.company_id,
        TallyUnit.is_active == True,
    ).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    was_synced = unit.tally_sync_status == "synced"
    if data.name is not None:
        unit.name = data.name.strip()
    if data.symbol is not None:
        sym = data.symbol.strip().replace(" ", "")[:8]
        if not sym:
            raise HTTPException(status_code=422, detail="Symbol cannot be empty")
        unit.symbol = sym
    if data.decimal_places is not None:
        unit.decimal_places = data.decimal_places
    unit.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="tally_unit", entity_id=unit.id,
                      description=f"Updated unit: {unit.name}")
    return {
        "id": str(unit.id), "name": unit.name, "tally_sync_status": unit.tally_sync_status,
        "warning": "Already synced to TallyPrime — update it there manually too." if was_synced else None,
    }


@router.delete("/units/{unit_id}")
def delete_unit(
    unit_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    unit = db.query(TallyUnit).filter(
        TallyUnit.id == uuid.UUID(unit_id),
        TallyUnit.company_id == current_user.company_id,
        TallyUnit.is_active == True,
    ).first()
    if not unit:
        raise HTTPException(status_code=404, detail="Unit not found")
    _cancel_pending_job(db, unit.tally_job_id)
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if connector and unit.tally_sync_status in ("synced", "finpilot", "delete_failed"):
        unit.tally_sync_status = "delete_pending"
        db.flush()
        _queue_tally_delete(db, current_user.company_id, TallyJobOperation.DELETE_UNIT, unit.name)
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_unit", entity_id=unit.id,
                          description=f"Delete queued for unit: {unit.name}")
        return {"status": "pending", "message": "Delete queued. The unit will be removed from FinPilot once TallyPrime confirms the deletion."}
    else:
        unit.is_active = False
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_unit", entity_id=unit.id,
                          description=f"Deleted unit: {unit.name}")
        return {"status": "deleted", "message": "Deleted successfully."}


# ─── Godown management ──────────────────────────────────────────────────────────

class GodownCreate(BaseModel):
    name: str
    parent: Optional[str] = None  # None = root location


@router.get("/godowns")
def list_godowns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyGodown).filter(
        TallyGodown.company_id == current_user.company_id,
        TallyGodown.is_active == True,
    )
    if search:
        q = q.filter(TallyGodown.name.ilike(f"%{search}%"))
    q = q.order_by(TallyGodown.name)
    result = _paginate(q, page, page_size)
    records = result["items"]
    if _reconcile_sync_status(db, records):
        db.commit()
    result["items"] = [
        {
            "id": str(r.id),
            "name": r.name,
            "parent": r.parent,
            "source": r.source,
            "tally_sync_status": r.tally_sync_status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return result


@router.post("/godowns")
def create_godown(
    data: GodownCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Godown name is required")

    key = _tally_key(current_user.company_id, name)
    existing = db.query(TallyGodown).filter(
        TallyGodown.company_id == current_user.company_id,
        TallyGodown.tally_key == key,
        TallyGodown.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Godown '{name}' already exists")

    godown = TallyGodown(
        company_id=current_user.company_id,
        name=name,
        parent=data.parent or None,
        tally_key=key,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(godown)
    db.flush()

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    tally_queued = False
    if connector:
        payload = {"name": name}
        if data.parent and data.parent.strip():
            payload["parent"] = data.parent.strip()
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_GODOWN,
            payload=payload,
            idempotency_key=f"create_godown::{godown.id}",
        )
        db.add(job)
        db.flush()
        godown.tally_job_id = job.id
        tally_queued = True

    db.commit()
    db.refresh(godown)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE,
        entity_type="tally_godown",
        entity_id=godown.id,
        description=f"Created Tally godown: {name}",
    )

    return {
        "id": str(godown.id),
        "name": godown.name,
        "parent": godown.parent,
        "tally_sync_status": godown.tally_sync_status,
        "tally_queued": tally_queued,
    }


class GodownUpdate(BaseModel):
    name: Optional[str] = None
    parent: Optional[str] = None


@router.patch("/godowns/{godown_id}")
def update_godown(
    godown_id: str,
    data: GodownUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    godown = db.query(TallyGodown).filter(
        TallyGodown.id == uuid.UUID(godown_id),
        TallyGodown.company_id == current_user.company_id,
        TallyGodown.is_active == True,
    ).first()
    if not godown:
        raise HTTPException(status_code=404, detail="Godown not found")
    was_synced = godown.tally_sync_status == "synced"
    if data.name is not None:
        godown.name = data.name.strip()
    if data.parent is not None:
        godown.parent = data.parent.strip() or None
    godown.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="tally_godown", entity_id=godown.id,
                      description=f"Updated godown: {godown.name}")
    return {
        "id": str(godown.id), "name": godown.name, "tally_sync_status": godown.tally_sync_status,
        "warning": "Already synced to TallyPrime — update it there manually too." if was_synced else None,
    }


@router.delete("/godowns/{godown_id}")
def delete_godown(
    godown_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    godown = db.query(TallyGodown).filter(
        TallyGodown.id == uuid.UUID(godown_id),
        TallyGodown.company_id == current_user.company_id,
        TallyGodown.is_active == True,
    ).first()
    if not godown:
        raise HTTPException(status_code=404, detail="Godown not found")
    _cancel_pending_job(db, godown.tally_job_id)
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if connector and godown.tally_sync_status in ("synced", "finpilot", "delete_failed"):
        godown.tally_sync_status = "delete_pending"
        db.flush()
        _queue_tally_delete(db, current_user.company_id, TallyJobOperation.DELETE_GODOWN, godown.name)
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_godown", entity_id=godown.id,
                          description=f"Delete queued for godown: {godown.name}")
        return {"status": "pending", "message": "Delete queued. The godown will be removed from FinPilot once TallyPrime confirms the deletion."}
    else:
        godown.is_active = False
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_godown", entity_id=godown.id,
                          description=f"Deleted godown: {godown.name}")
        return {"status": "deleted", "message": "Deleted successfully."}


# ─── Stock Item management ───────────────────────────────────────────────────────

class StockItemCreate(BaseModel):
    name: str
    stock_group: Optional[str] = None
    stock_category: Optional[str] = None
    unit: Optional[str] = None
    rate: Optional[float] = 0.0
    opening_qty: Optional[float] = 0.0


class StockItemUpdate(BaseModel):
    name: Optional[str] = None
    stock_group: Optional[str] = None
    stock_category: Optional[str] = None
    unit: Optional[str] = None
    rate: Optional[float] = None


@router.get("/stock-items")
def list_stock_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyStockItem).filter(
        TallyStockItem.company_id == current_user.company_id,
        TallyStockItem.is_active == True,
        TallyStockItem.tally_sync_status != 'failed',
    )
    if search:
        q = q.filter(TallyStockItem.name.ilike(f"%{search}%"))
    q = q.order_by(TallyStockItem.name)
    result = _paginate(q, page, page_size)
    records = result["items"]
    if _reconcile_sync_status(db, records):
        db.commit()
    result["items"] = [
        {
            "id": str(r.id),
            "name": r.name,
            "stock_group": r.stock_group,
            "stock_category": getattr(r, "stock_category", None),
            "unit": r.unit,
            "rate": r.rate,
            "opening_qty": r.opening_qty if r.opening_qty else 0,
            "source": r.source,
            "tally_sync_status": r.tally_sync_status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return result


@router.post("/stock-items")
def create_stock_item(
    data: StockItemCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Stock item name is required")

    key = _tally_key(current_user.company_id, name)
    existing = db.query(TallyStockItem).filter(
        TallyStockItem.company_id == current_user.company_id,
        TallyStockItem.tally_key == key,
        TallyStockItem.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Stock item '{name}' already exists")

    item = TallyStockItem(
        company_id=current_user.company_id,
        name=name,
        stock_group=data.stock_group or None,
        stock_category=data.stock_category or None,
        unit=data.unit or None,
        rate=data.rate or 0.0,
        opening_qty=data.opening_qty or 0.0,
        tally_key=key,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(item)
    db.flush()

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    tally_queued = False
    if connector:
        payload = {
            "name": name,
            "unit": data.unit or "",
            "rate": str(data.rate or 0),
            "opening_qty": str(data.opening_qty or 0),
        }
        if data.stock_group:
            payload["stock_group"] = data.stock_group
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_STOCK_ITEM,
            payload=payload,
            idempotency_key=f"create_stock_item::{item.id}",
        )
        db.add(job)
        db.flush()
        item.tally_job_id = job.id
        tally_queued = True

    db.commit()
    db.refresh(item)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE,
        entity_type="tally_stock_item",
        entity_id=item.id,
        description=f"Created Tally stock item: {name}",
    )

    return {
        "id": str(item.id),
        "name": item.name,
        "stock_group": item.stock_group,
        "stock_category": item.stock_category,
        "unit": item.unit,
        "rate": item.rate,
        "tally_sync_status": item.tally_sync_status,
        "tally_queued": tally_queued,
    }


@router.patch("/stock-items/{item_id}")
def update_stock_item(
    item_id: str,
    data: StockItemUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    item = db.query(TallyStockItem).filter(
        TallyStockItem.id == uuid.UUID(item_id),
        TallyStockItem.company_id == current_user.company_id,
        TallyStockItem.is_active == True,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Stock item not found")
    was_synced = item.tally_sync_status == "synced"
    if data.name is not None:
        item.name = data.name.strip()
    if data.stock_group is not None:
        item.stock_group = data.stock_group.strip() or None
    if data.stock_category is not None:
        item.stock_category = data.stock_category.strip() or None
    if data.unit is not None:
        item.unit = data.unit.strip() or None
    if data.rate is not None:
        item.rate = data.rate
    item.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="tally_stock_item", entity_id=item.id,
                      description=f"Updated stock item: {item.name}")
    return {
        "id": str(item.id), "name": item.name, "tally_sync_status": item.tally_sync_status,
        "warning": "Already synced to TallyPrime — update it there manually too." if was_synced else None,
    }


@router.delete("/stock-items/{item_id}")
def delete_stock_item(
    item_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    item = db.query(TallyStockItem).filter(
        TallyStockItem.id == uuid.UUID(item_id),
        TallyStockItem.company_id == current_user.company_id,
        TallyStockItem.is_active == True,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Stock item not found")
    _cancel_pending_job(db, item.tally_job_id)
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if connector and item.tally_sync_status in ("synced", "finpilot", "delete_failed"):
        item.tally_sync_status = "delete_pending"
        db.flush()
        _queue_tally_delete(db, current_user.company_id, TallyJobOperation.DELETE_STOCK_ITEM, item.name)
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_stock_item", entity_id=item.id,
                          description=f"Delete queued for stock item: {item.name}")
        return {"status": "pending", "message": "Delete queued. The item will be removed from FinPilot once TallyPrime confirms deletion."}
    else:
        item.is_active = False
        db.commit()
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                          entity_type="tally_stock_item", entity_id=item.id,
                          description=f"Deleted stock item: {item.name}")
        return {"status": "deleted", "message": "Deleted successfully."}


# ─── Unified voucher view ────────────────────────────────────────────────────────

VOUCHER_TYPE_FILTER = {
    "sales": "SALES",
    "purchase": "PURCHASE",
}


@router.get("/vouchers")
def list_vouchers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    voucher_type: Optional[str] = Query(None, description="ALL|SALES|PURCHASE|EXPENSE|PAYMENT"),
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    ledger_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    results = []

    # ── Invoices (SALES / PURCHASE) ──────────────────────────────────────────
    from app.models.tally_masters import TallyVoucherType as _TVT
    vt = (voucher_type or "").upper()

    _STANDARD_TYPES = {
        "SALES", "PURCHASE", "RECEIPT", "PAYMENT", "CONTRA", "JOURNAL",
        "CREDIT NOTE", "DEBIT NOTE", "SALES ORDER", "PURCHASE ORDER",
        "DELIVERY NOTE", "RECEIPT NOTE", "STOCK JOURNAL", "PHYSICAL STOCK",
        "REVERSING JOURNAL", "MEMORANDUM", "ATTENDANCE", "PAYROLL",
        "MATERIAL IN", "MATERIAL OUT", "REJECTIONS IN", "REJECTIONS OUT",
        "JOB WORK IN ORDER", "JOB WORK OUT ORDER",
    }

    # Build full map: uppercase name → (original name, parent) for custom types
    _all_vtypes = db.query(_TVT).filter(
        _TVT.company_id == cid, _TVT.is_active == True,
    ).all()
    _custom_vtype_map = {
        r.name.upper(): {"name": r.name, "parent": r.parent or ""}
        for r in _all_vtypes
        if r.name.upper() not in _STANDARD_TYPES
    }
    _custom_vtype_names_upper = set(_custom_vtype_map.keys())

    include_invoices = vt in ("", "ALL", "SALES", "PURCHASE")
    include_expenses = vt in (
        "", "ALL", "PAYMENT", "PURCHASE", "DEBIT_NOTE",
        "RECEIPT", "JOURNAL", "CONTRA", "CREDIT_NOTE",
    ) or vt in _custom_vtype_names_upper or vt == "CUSTOM"

    if include_invoices:
        inv_q = db.query(Invoice).options(
            joinedload(Invoice.customer),
            joinedload(Invoice.vendor),
        ).filter(Invoice.company_id == cid, Invoice.is_deleted.is_not(True))
        if vt == "SALES":
            inv_q = inv_q.filter(Invoice.invoice_type == InvoiceType.SALES)
        elif vt == "PURCHASE":
            inv_q = inv_q.filter(Invoice.invoice_type == InvoiceType.PURCHASE)
        if date_from:
            try:
                inv_q = inv_q.filter(Invoice.invoice_date >= datetime.fromisoformat(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                inv_q = inv_q.filter(Invoice.invoice_date <= datetime.fromisoformat(date_to))
            except ValueError:
                pass

        for inv in inv_q.all():
            party_name = (
                (inv.customer.name if inv.customer else None) or
                (inv.vendor.name if inv.vendor else None)
            )
            inv_sync = getattr(inv, "tally_sync_status", None) or "local_only"
            inv_notes = getattr(inv, "notes", None) or ""
            inv_source = "tally_sync" if "[tally-sync]" in inv_notes else "finpilot"
            results.append({
                "id": str(inv.id),
                "voucher_number": inv.invoice_number,
                "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "voucher_type": inv.invoice_type.value if inv.invoice_type else "INVOICE",
                "party": inv.customer_id and str(inv.customer_id),
                "party_name": party_name,
                "amount": float(inv.total_amount or 0),
                "status": inv.status.value if inv.status else "DRAFT",
                "source": inv_source,
                "tally_sync_status": inv_sync,
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "entity_type": "invoice",
                "paid_amount": float(inv.paid_amount or 0),
            })

    if include_expenses:
        exp_q = db.query(Expense).options(
            joinedload(Expense.vendor),
        ).filter(Expense.company_id == cid, Expense.is_deleted.is_not(True))
        if date_from:
            try:
                exp_q = exp_q.filter(Expense.expense_date >= datetime.fromisoformat(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                exp_q = exp_q.filter(Expense.expense_date <= datetime.fromisoformat(date_to))
            except ValueError:
                pass

        # Map category → voucher type for display and filtering
        _cat_to_vtype = {
            "Purchase": "PURCHASE",
            "Purchase Return": "DEBIT_NOTE",
            "Payment": "PAYMENT",
            "Receipt": "RECEIPT",
            "Journal": "JOURNAL",
            "Contra": "CONTRA",
            "Credit Note": "CREDIT_NOTE",
            "Debit Note": "DEBIT_NOTE",
        }
        for exp in exp_q.all():
            exp_sync = getattr(exp, "tally_sync_status", None) or "local_only"
            exp_notes = getattr(exp, "notes", None) or ""
            exp_source = "tally_sync" if "[tally-sync]" in exp_notes else "finpilot"
            raw_cat = exp.category or ""
            is_custom = raw_cat.upper() in _custom_vtype_names_upper
            exp_vtype = _cat_to_vtype.get(raw_cat, raw_cat.upper() if raw_cat else "PAYMENT")

            # CUSTOM filter: only include expenses whose category is a custom voucher type
            if vt == "CUSTOM":
                if not is_custom:
                    continue
            elif vt and vt not in ("", "ALL") and exp_vtype.upper() != vt.upper():
                continue

            # Extract party name from notes ("Party: ABC Traders | Type: GST Bill")
            party_from_notes = ""
            if "Party: " in exp_notes:
                try:
                    party_from_notes = exp_notes.split("Party: ")[1].split(" |")[0].strip()
                except Exception:
                    pass
            display_name = party_from_notes or (exp.vendor.name if exp.vendor else None) or exp.title

            # Custom type metadata
            custom_meta = _custom_vtype_map.get(raw_cat.upper(), {})
            results.append({
                "id": str(exp.id),
                "voucher_number": exp.reference_number or f"EXP-{str(exp.id)[:8].upper()}",
                "date": exp.expense_date.isoformat() if exp.expense_date else None,
                "voucher_type": exp_vtype,
                "party": None,
                "party_name": display_name,
                "amount": float(exp.amount or 0),
                "status": exp.status.value if exp.status else "DRAFT",
                "source": exp_source,
                "tally_sync_status": exp_sync,
                "created_at": exp.created_at.isoformat() if exp.created_at else None,
                "entity_type": "expense",
                "title": exp.title,
                "paid_amount": 0,
                # Custom voucher type fields
                "is_custom_voucher": is_custom,
                "custom_type_name": custom_meta.get("name", raw_cat) if is_custom else None,
                "parent_type": custom_meta.get("parent", "") if is_custom else None,
            })

    # Unified case-insensitive search across all fields
    if search:
        sl = search.lower()
        results = [
            r for r in results
            if sl in (r.get("voucher_number") or "").lower()
            or sl in (r.get("party_name") or "").lower()
            or sl in (r.get("title") or "").lower()
            or sl in (r.get("voucher_type") or "").lower()
            or sl in (r.get("status") or "").lower()
        ]

    # Apply ledger_name filter (match against party name or title)
    if ledger_name:
        lf = ledger_name.lower()
        results = [
            r for r in results
            if lf in (r.get("party_name") or "").lower()
            or lf in (r.get("title") or "").lower()
        ]

    # Sort by date desc
    results.sort(key=lambda x: x.get("date") or x.get("created_at") or "", reverse=True)

    # Paginate in-memory
    total = len(results)
    start = (page - 1) * page_size
    end = start + page_size
    items = results[start:end]

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size),
    }


def _extract_tally_vnum_from_notes(notes: str) -> str:
    """Extract actual TallyPrime voucher number from '[tally-sync] VType::VNUM' notes.

    Returns empty string when notes use the fallback dedup format (no real voucher number).
    """
    tag = "[tally-sync]"
    if not notes or tag not in notes:
        return ""
    after = notes[notes.find(tag) + len(tag):].strip()
    parts = after.split("::", 1)
    if len(parts) < 2:
        return ""
    vnum = parts[1].strip()
    # Fallback dedup key format uses additional "::" separators (type::date::party::amount)
    return vnum if "::" not in vnum else ""


def _queue_tally_delete_voucher(
    db: Session,
    company_id: uuid.UUID,
    voucher_ref: str,
    voucher_type: str,
    entity_type: str,
    voucher_date: str = "",
    voucher_number: str = "",
    entity_id: str = "",
) -> bool:
    """Queue a DELETE_VOUCHER job to permanently remove the voucher from TallyPrime.
    Returns True if queued, False if no active connector.

    voucher_ref    – REMOTEID (FP-xxxx) for FinPilot-created vouchers.
    voucher_number – TallyPrime voucher number for Tally-native vouchers.
    entity_id      – FinPilot record UUID so the callback can find the record by ID.
    """
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()
    if not connector:
        return False
    import secrets as _sec
    ref_key = voucher_ref or voucher_number or "unknown"
    ikey = f"delete_voucher::{ref_key}::{_sec.token_hex(4)}"
    db.add(TallyIntegrationJob(
        company_id=company_id,
        connector_id=connector.id,
        operation=TallyJobOperation.DELETE_VOUCHER,
        payload={
            "voucher_ref":    voucher_ref,
            "voucher_number": voucher_number,
            "voucher_type":   voucher_type,
            "entity_type":    entity_type,
            "date":           voucher_date,
            "entity_id":      entity_id,
        },
        idempotency_key=ikey,
    ))
    return True


@router.delete("/vouchers/{entity_type}/{entity_id}")
def delete_voucher(
    entity_type: str,
    entity_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    """
    Tally-confirmed-first delete for vouchers.

    Flow for Tally-synced records:
      1. Queue DELETE_VOUCHER job → connector → TallyPrime (permanent delete, not just cancel)
      2. Mark record as delete_pending (still visible in FinPilot)
      3. When TallyPrime confirms deletion → tally.py result handler soft-deletes the FinPilot record

    Flow for local-only records (never sent to Tally):
      Immediate soft-delete in FinPilot.

    Records without tally_voucher_ref (created before Tally sync tracking):
      Immediate soft-delete with a warning to manually cancel in TallyPrime.
    """
    cid = current_user.company_id

    if entity_type == "invoice":
        record = db.query(Invoice).filter(
            Invoice.id == uuid.UUID(entity_id),
            Invoice.company_id == cid,
            Invoice.is_deleted.is_not(True),
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Invoice not found")
        if float(record.paid_amount or 0) > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete: ₹{float(record.paid_amount):,.2f} in payments are recorded against this invoice. Remove the payments first.",
            )

        voucher_status = getattr(record, "tally_sync_status", "local_only") or "local_only"
        raw_vref       = getattr(record, "tally_voucher_ref", None) or ""
        voucher_type_tally = "Sales" if record.invoice_type and record.invoice_type.value == "SALES" else "Purchase"
        inv_number     = record.invoice_number or ""

        inv_date = ""
        if record.invoice_date:
            try:
                inv_date = record.invoice_date.strftime("%Y%m%d")
            except Exception:
                pass

        # Distinguish REMOTEID (FinPilot-created, "FP-xxxx") from Tally voucher number
        # (Tally-native, stored in tally_voucher_ref after the sync-service fix, or
        # embedded in notes for records synced before the fix).
        is_tally_native = "[tally-sync]" in (record.notes or "")
        if is_tally_native:
            # tally_voucher_ref holds the actual Tally voucher number (new syncs)
            # or we fall back to extracting it from notes (pre-fix syncs).
            voucher_ref = ""
            tally_vnum  = raw_vref or _extract_tally_vnum_from_notes(record.notes or "")
        else:
            voucher_ref = raw_vref   # REMOTEID (FP-xxxx)
            tally_vnum  = ""

        # ── Case 1: Synced (or previous cancel failed) — MUST cancel in TallyPrime first
        # Covers both FinPilot-created (has REMOTEID) and Tally-native (has VOUCHERNUMBER only).
        if voucher_status in ("synced", "delete_failed"):
            if not voucher_ref and not tally_vnum:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Cannot delete: invoice has no TallyPrime reference. "
                        "Cancel it in TallyPrime manually, then delete here."
                    ),
                )
            record.tally_sync_status = "delete_pending"
            db.flush()
            queued = _queue_tally_delete_voucher(
                db, cid,
                voucher_ref=voucher_ref,
                voucher_type=voucher_type_tally,
                entity_type="invoice",
                voucher_date=inv_date,
                voucher_number=tally_vnum,
                entity_id=str(record.id),
            )
            db.commit()
            audit_service.log(db, cid, current_user.id, AuditAction.DELETE,
                              entity_type="invoice", entity_id=record.id,
                              description=f"Cancel queued for invoice: {inv_number}")
            if queued:
                return {
                    "status": "pending",
                    "tally_confirmed": False,
                    "message": (
                        f"Cancel request sent to TallyPrime for {inv_number}. "
                        "The invoice will be removed from FinPilot once TallyPrime confirms."
                    ),
                }
            # No active connector — inform user; keep record visible
            record.tally_sync_status = voucher_status   # restore
            db.commit()
            raise HTTPException(
                status_code=409,
                detail=(
                    f"No active TallyPrime connector. "
                    f"Cancel invoice {inv_number} in TallyPrime first, then delete here — "
                    "or connect the TallyPrime connector and retry."
                ),
            )

        # ── Case 2: Pending (queued for creation, not yet confirmed by TallyPrime)
        # Cancel the in-flight create job so TallyPrime doesn't process it.
        elif voucher_status == "pending":
            if record.tally_voucher_ref:
                # Cancel any pending create job for this ref
                from app.models.tally_job import TallyJobOperation as _TJO
                pending_jobs = db.query(TallyIntegrationJob).filter(
                    TallyIntegrationJob.company_id == cid,
                    TallyIntegrationJob.status == JobStatus.PENDING,
                    TallyIntegrationJob.operation.in_([
                        _TJO.CREATE_SALES_VOUCHER, _TJO.CREATE_PURCHASE_VOUCHER,
                    ]),
                ).all()
                for j in pending_jobs:
                    if (j.payload or {}).get("voucher_number") == record.tally_voucher_ref:
                        j.status = JobStatus.CANCELLED
            record.is_deleted = True
            db.commit()
            audit_service.log(db, cid, current_user.id, AuditAction.DELETE,
                              entity_type="invoice", entity_id=record.id,
                              description=f"Deleted pending invoice: {inv_number}")
            return {
                "status": "deleted",
                "tally_confirmed": False,
                "message": (
                    f"Invoice {inv_number} removed from FinPilot. "
                    "The pending TallyPrime create job was cancelled."
                ),
            }

        # ── Case 3: Local-only — never reached TallyPrime, safe to delete immediately
        else:
            record.is_deleted = True
            db.commit()
            audit_service.log(db, cid, current_user.id, AuditAction.DELETE,
                              entity_type="invoice", entity_id=record.id,
                              description=f"Deleted local invoice: {inv_number}")
            return {
                "status": "deleted",
                "tally_confirmed": False,
                "message": f"Invoice {inv_number} removed from FinPilot.",
            }

    elif entity_type == "expense":
        record = db.query(Expense).filter(
            Expense.id == uuid.UUID(entity_id),
            Expense.company_id == cid,
            Expense.is_deleted.is_not(True),
        ).first()
        if not record:
            raise HTTPException(status_code=404, detail="Expense not found")

        voucher_status = getattr(record, "tally_sync_status", "local_only") or "local_only"
        raw_vref_exp   = getattr(record, "tally_voucher_ref", None) or ""
        exp_title      = record.title or ""

        exp_date = ""
        if record.expense_date:
            try:
                exp_date = record.expense_date.strftime("%Y%m%d")
            except Exception:
                pass

        # Distinguish REMOTEID vs Tally voucher number (same logic as invoice branch)
        is_tally_native_exp = "[tally-sync]" in (record.notes or "")
        if is_tally_native_exp:
            exp_voucher_ref = ""
            exp_tally_vnum  = raw_vref_exp or _extract_tally_vnum_from_notes(record.notes or "")
        else:
            exp_voucher_ref = raw_vref_exp   # REMOTEID
            exp_tally_vnum  = ""

        # Guess the correct Tally voucher type from the expense category
        _EXP_VTYPE_MAP = {
            "Purchase": "Purchase", "Receipt": "Receipt", "Payment": "Payment",
            "Credit Note": "Credit Note", "Debit Note": "Debit Note",
            "Contra": "Contra", "Journal": "Journal",
        }
        exp_voucher_type = _EXP_VTYPE_MAP.get(record.category or "", "Purchase")

        # ── Case 1: Synced (or previous cancel failed) — MUST cancel in TallyPrime first
        if voucher_status in ("synced", "delete_failed"):
            if not exp_voucher_ref and not exp_tally_vnum:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Cannot delete: expense has no TallyPrime reference. "
                        "Cancel it in TallyPrime manually, then delete here."
                    ),
                )
            record.tally_sync_status = "delete_pending"
            db.flush()
            queued = _queue_tally_delete_voucher(
                db, cid,
                voucher_ref=exp_voucher_ref,
                voucher_type=exp_voucher_type,
                entity_type="expense",
                voucher_date=exp_date,
                voucher_number=exp_tally_vnum,
                entity_id=str(record.id),
            )
            db.commit()
            audit_service.log(db, cid, current_user.id, AuditAction.DELETE,
                              entity_type="expense", entity_id=record.id,
                              description=f"Cancel queued for expense: {exp_title}")
            if queued:
                return {
                    "status": "pending",
                    "tally_confirmed": False,
                    "message": (
                        f"Cancel request sent to TallyPrime for '{exp_title}'. "
                        "The expense will be removed from FinPilot once TallyPrime confirms."
                    ),
                }
            # No active connector — inform user; keep record visible
            record.tally_sync_status = voucher_status   # restore
            db.commit()
            raise HTTPException(
                status_code=409,
                detail=(
                    f"No active TallyPrime connector. "
                    f"Cancel expense '{exp_title}' in TallyPrime first, then delete here — "
                    "or connect the TallyPrime connector and retry."
                ),
            )

        # ── Case 2: Pending (queued for creation, not yet confirmed by TallyPrime)
        elif voucher_status == "pending":
            if record.tally_voucher_ref:
                from app.models.tally_job import TallyJobOperation as _TJO
                pending_jobs = db.query(TallyIntegrationJob).filter(
                    TallyIntegrationJob.company_id == cid,
                    TallyIntegrationJob.status == JobStatus.PENDING,
                    TallyIntegrationJob.operation.in_([
                        _TJO.CREATE_PURCHASE_VOUCHER,
                    ]),
                ).all()
                for j in pending_jobs:
                    if (j.payload or {}).get("voucher_number") == record.tally_voucher_ref:
                        j.status = JobStatus.CANCELLED
            record.is_deleted = True
            db.commit()
            audit_service.log(db, cid, current_user.id, AuditAction.DELETE,
                              entity_type="expense", entity_id=record.id,
                              description=f"Deleted pending expense: {exp_title}")
            return {
                "status": "deleted",
                "tally_confirmed": False,
                "message": (
                    f"Expense '{exp_title}' removed from FinPilot. "
                    "The pending TallyPrime create job was cancelled."
                ),
            }

        # ── Case 3: Local-only — never reached TallyPrime, safe to delete immediately
        else:
            record.is_deleted = True
            db.commit()
            audit_service.log(db, cid, current_user.id, AuditAction.DELETE,
                              entity_type="expense", entity_id=record.id,
                              description=f"Deleted local expense: {exp_title}")
            return {
                "status": "deleted",
                "tally_confirmed": False,
                "message": f"Expense '{exp_title}' removed from FinPilot.",
            }

    else:
        raise HTTPException(status_code=400, detail="entity_type must be 'invoice' or 'expense'")


# ─── Voucher Type management ─────────────────────────────────────────────────────

BASE_VOUCHER_TYPES = [
    # Core accounting
    "Sales", "Purchase", "Receipt", "Payment", "Journal", "Contra",
    "Credit Note", "Debit Note", "Reversing Journal", "Memorandum",
    # Orders
    "Sales Order", "Purchase Order",
    # Inventory / Stock
    "Stock Journal", "Physical Stock", "Delivery Note", "Receipt Note",
    "Material In", "Material Out", "Rejections In", "Rejections Out",
    # Job Work
    "Job Work In Order", "Job Work Out Order",
    # HR
    "Attendance", "Payroll",
]


class VoucherTypeCreate(BaseModel):
    name: str
    parent: str          # base TallyPrime type (Sales, Purchase, etc.)
    numbering_method: Optional[str] = "Automatic"


@router.get("/voucher-types")
def list_voucher_types(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyVoucherType).filter(
        TallyVoucherType.company_id == current_user.company_id,
        TallyVoucherType.is_active == True,
    )
    if search:
        q = q.filter(TallyVoucherType.name.ilike(f"%{search}%"))
    q = q.order_by(TallyVoucherType.parent, TallyVoucherType.name)
    result = _paginate(q, page, page_size)
    records = result["items"]
    if _reconcile_sync_status(db, records):
        db.commit()
    result["items"] = [
        {
            "id": str(r.id),
            "name": r.name,
            "parent": r.parent,
            "numbering_method": r.numbering_method,
            "source": r.source,
            "tally_sync_status": r.tally_sync_status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return result


@router.post("/voucher-types")
def create_voucher_type(
    data: VoucherTypeCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Voucher type name is required")
    if data.parent not in BASE_VOUCHER_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Parent must be one of: {', '.join(BASE_VOUCHER_TYPES)}",
        )

    key = _tally_key(current_user.company_id, name)
    existing = db.query(TallyVoucherType).filter(
        TallyVoucherType.company_id == current_user.company_id,
        TallyVoucherType.tally_key == key,
        TallyVoucherType.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Voucher type '{name}' already exists")

    vt = TallyVoucherType(
        company_id=current_user.company_id,
        name=name,
        parent=data.parent,
        numbering_method=data.numbering_method or "Automatic",
        tally_key=key,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(vt)
    db.flush()

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    tally_queued = False
    if connector:
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_VOUCHER_TYPE,
            payload={
                "name": name,
                "parent": data.parent,
                "numbering_method": data.numbering_method or "Automatic",
            },
            idempotency_key=f"create_voucher_type::{vt.id}",
        )
        db.add(job)
        db.flush()
        vt.tally_job_id = job.id
        tally_queued = True

    db.commit()
    db.refresh(vt)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE, entity_type="tally_voucher_type", entity_id=vt.id,
        description=f"Created voucher type: {name} (based on {data.parent})",
    )

    return {
        "id": str(vt.id),
        "name": vt.name,
        "parent": vt.parent,
        "numbering_method": vt.numbering_method,
        "tally_sync_status": vt.tally_sync_status,
        "tally_queued": tally_queued,
    }


@router.delete("/voucher-types/{vt_id}")
def delete_voucher_type(
    vt_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    vt = db.query(TallyVoucherType).filter(
        TallyVoucherType.id == uuid.UUID(vt_id),
        TallyVoucherType.company_id == current_user.company_id,
        TallyVoucherType.is_active == True,
    ).first()
    if not vt:
        raise HTTPException(status_code=404, detail="Voucher type not found")
    if vt.source == "tally_sync" and vt.parent is None:
        raise HTTPException(status_code=400, detail="Built-in TallyPrime voucher types cannot be deleted from FinPilot.")

    # Cancel any pending create job first
    _cancel_pending_job(db, vt.tally_job_id)

    # If this type was synced to TallyPrime, delete from Tally first (confirmed-first pattern)
    if vt.tally_sync_status == "synced":
        queued = _queue_tally_delete(
            db, current_user.company_id,
            TallyJobOperation.DELETE_VOUCHER_TYPE,
            vt.name,
        )
        if queued:
            vt.tally_sync_status = "delete_pending"
            db.commit()
            audit_service.log(
                db, current_user.company_id, current_user.id, AuditAction.DELETE,
                entity_type="tally_voucher_type", entity_id=vt.id,
                description=f"Voucher type delete queued for TallyPrime: {vt.name}",
            )
            return {
                "status": "pending",
                "message": f"Delete sent to TallyPrime. '{vt.name}' will be removed once TallyPrime confirms.",
            }

    # No active connector or not yet synced — remove locally immediately
    vt.is_active = False
    db.commit()
    audit_service.log(
        db, current_user.company_id, current_user.id, AuditAction.DELETE,
        entity_type="tally_voucher_type", entity_id=vt.id,
        description=f"Deleted voucher type locally: {vt.name}",
    )
    return {"status": "deleted", "message": "Deleted successfully."}


# ─── Wipe ALL vouchers (invoices + expenses) for the company ─────────────────────

@router.post("/wipe-vouchers")
def wipe_all_vouchers(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Hard-wipe every invoice and expense for this company so the user can
    start fresh with a clean sync from TallyPrime.
    Only voucher data is touched — ledgers, customers, vendors, stock, etc. are untouched.
    """
    deleted_invoices = db.query(Invoice).filter(
        Invoice.company_id == current_user.company_id,
        Invoice.is_deleted.is_not(True),
    ).update({"is_deleted": True}, synchronize_session=False)

    deleted_expenses = db.query(Expense).filter(
        Expense.company_id == current_user.company_id,
        Expense.is_deleted.is_not(True),
    ).update({"is_deleted": True}, synchronize_session=False)

    db.commit()

    audit_service.log(
        db, current_user.company_id, current_user.id, AuditAction.DELETE,
        entity_type="voucher_wipe",
        description=f"Wiped all vouchers: {deleted_invoices} invoices, {deleted_expenses} expenses",
    )

    return {
        "deleted_invoices": deleted_invoices,
        "deleted_expenses": deleted_expenses,
        "message": f"Wiped {deleted_invoices} invoice(s) and {deleted_expenses} expense(s). All Vouchers is now empty. Run a full sync to import from TallyPrime.",
    }


# ─── Wipe ALL local FinPilot data (pre-sync reset) ──────────────────────────────

@router.post("/wipe-all-local-data")
def wipe_all_local_data(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Wipe every entity stored locally in FinPilot for this company so the user
    can start with a clean slate and re-import everything from TallyPrime via Sync.

    Deletes (soft or hard):
      - Invoices (Sales / Purchase)
      - Expenses (Receipt / Payment / Journal / Contra / Credit Note / Debit Note)
      - Stock transactions (all types)
      - Voucher types (custom + base)
      - Ledgers, Account groups
      - Stock groups, Stock items, Stock categories
      - Units, Godowns

    Does NOT delete: customers, vendors, users, company settings, audit logs,
    payments recorded against invoices, or TallyPrime connector pairing.
    """
    from app.models.stock_transaction import StockTransaction
    from app.models.stock_category import StockCategory

    cid = current_user.company_id

    # ── Vouchers (invoices + expenses) ───────────────────────────────────────
    del_invoices  = db.query(Invoice).filter(Invoice.company_id == cid,  Invoice.is_deleted.is_not(True)) \
                      .update({"is_deleted": True}, synchronize_session=False)
    del_expenses  = db.query(Expense).filter(Expense.company_id == cid,  Expense.is_deleted.is_not(True)) \
                      .update({"is_deleted": True}, synchronize_session=False)

    # ── Stock transactions ────────────────────────────────────────────────────
    del_stxns     = db.query(StockTransaction).filter(StockTransaction.company_id == cid,
                        StockTransaction.is_active.is_not(False)) \
                      .update({"is_active": False}, synchronize_session=False)

    # ── Tally master entities (soft-delete via is_active) ────────────────────
    del_vtypes    = db.query(TallyVoucherType).filter(TallyVoucherType.company_id == cid,
                        TallyVoucherType.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)
    del_ledgers   = db.query(TallyLedger).filter(TallyLedger.company_id == cid,
                        TallyLedger.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)
    del_groups    = db.query(TallyGroup).filter(TallyGroup.company_id == cid,
                        TallyGroup.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)
    del_sgroups   = db.query(TallyStockGroup).filter(TallyStockGroup.company_id == cid,
                        TallyStockGroup.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)
    del_sitems    = db.query(TallyStockItem).filter(TallyStockItem.company_id == cid,
                        TallyStockItem.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)
    del_scats     = db.query(StockCategory).filter(StockCategory.company_id == cid,
                        StockCategory.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)
    del_units     = db.query(TallyUnit).filter(TallyUnit.company_id == cid,
                        TallyUnit.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)
    del_godowns   = db.query(TallyGodown).filter(TallyGodown.company_id == cid,
                        TallyGodown.is_active == True) \
                      .update({"is_active": False}, synchronize_session=False)

    db.commit()

    audit_service.log(
        db, cid, current_user.id, AuditAction.DELETE,
        entity_type="wipe_all_local_data",
        description=(
            f"Wiped all local data: {del_invoices} invoices, {del_expenses} expenses, "
            f"{del_stxns} stock transactions, {del_vtypes} voucher types, "
            f"{del_ledgers} ledgers, {del_groups} account groups, "
            f"{del_sgroups} stock groups, {del_sitems} stock items, "
            f"{del_scats} stock categories, {del_units} units, {del_godowns} godowns"
        ),
    )

    return {
        "invoices":          del_invoices,
        "expenses":          del_expenses,
        "stock_transactions": del_stxns,
        "voucher_types":     del_vtypes,
        "ledgers":           del_ledgers,
        "account_groups":    del_groups,
        "stock_groups":      del_sgroups,
        "stock_items":       del_sitems,
        "stock_categories":  del_scats,
        "units":             del_units,
        "godowns":           del_godowns,
        "message": "All local data wiped. Click Sync Now to re-import everything from TallyPrime.",
    }


# ─── Clear local-only vouchers ───────────────────────────────────────────────────

@router.post("/clear-local-vouchers")
def clear_local_vouchers(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Soft-delete all invoices and expenses that were created locally in FinPilot
    and have never been synced to or imported from TallyPrime.
    Safe to run before a full Tally sync to get a clean slate.
    """
    from app.models.invoice import Invoice
    from app.models.expense import Expense
    TALLY_TAG = "[tally-sync]"
    cid = current_user.company_id

    # Delete all invoices NOT imported from TallyPrime.
    # notes IS NULL  → locally created, never tagged
    # notes NOT LIKE '%[tally-sync]%' → created in FinPilot, not from Tally
    local_invoices = db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.is_deleted.is_not(True),
        or_(
            Invoice.notes.is_(None),
            ~Invoice.notes.like(f"%{TALLY_TAG}%"),
        ),
    ).all()
    deleted_invoices = len(local_invoices)
    for inv in local_invoices:
        inv.is_deleted = True

    # Same for expenses
    local_expenses = db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.is_deleted.is_not(True),
        or_(
            Expense.notes.is_(None),
            ~Expense.notes.like(f"%{TALLY_TAG}%"),
        ),
    ).all()
    deleted_expenses = len(local_expenses)
    for exp in local_expenses:
        exp.is_deleted = True

    db.commit()

    audit_service.log(
        db, cid, current_user.id, AuditAction.DELETE,
        entity_type="voucher_cleanup",
        description=f"Cleared {deleted_invoices} local invoices and {deleted_expenses} local expenses",
    )

    return {
        "deleted_invoices": deleted_invoices,
        "deleted_expenses": deleted_expenses,
        "message": f"Removed {deleted_invoices} local invoice(s) and {deleted_expenses} local expense(s). Run a full sync to import data from TallyPrime.",
    }


# ─── Sync health ─────────────────────────────────────────────────────────────────

@router.get("/sync-health")
def get_sync_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id

    total_jobs = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid
    ).scalar() or 0

    successful = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.SUCCESS,
    ).scalar() or 0

    failed = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.FAILED,
    ).scalar() or 0

    pending = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status.in_([JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RUNNING]),
    ).scalar() or 0

    retrying = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.RETRYING,
    ).scalar() or 0

    last_success = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.SUCCESS,
    ).order_by(TallyIntegrationJob.completed_at.desc()).first()

    recent_jobs = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.company_id == cid,
    ).order_by(TallyIntegrationJob.created_at.desc()).limit(50).all()

    return {
        "total_jobs": total_jobs,
        "successful": successful,
        "failed": failed,
        "pending": pending,
        "retrying": retrying,
        "last_successful_sync": last_success.completed_at.isoformat() if last_success and last_success.completed_at else None,
        "recent_jobs": [
            {
                "id": str(j.id),
                "operation": j.operation.value,
                "status": j.status.value,
                "retry_count": j.retry_count,
                "error_message": j.error_message,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in recent_jobs
        ],
    }


# ─── Account Group management ──────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str
    parent: Optional[str] = None
    nature: Optional[str] = None  # assets | liabilities | income | expenses


@router.get("/groups")
def list_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyGroup).filter(
        TallyGroup.company_id == current_user.company_id,
        TallyGroup.is_active == True,
    )
    if search:
        q = q.filter(TallyGroup.name.ilike(f"%{search}%"))
    q = q.order_by(TallyGroup.name)
    result = _paginate(q, page, page_size)
    records = result["items"]
    if _reconcile_sync_status(db, records):
        db.commit()
    result["items"] = [
        {
            "id": str(r.id),
            "name": r.name,
            "parent": r.parent,
            "nature": r.nature,
            "source": r.source,
            "tally_sync_status": r.tally_sync_status,
            "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]
    return result


@router.post("/groups")
def create_group(
    data: GroupCreate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    name = data.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Group name is required")

    key = _tally_key(current_user.company_id, name)
    existing = db.query(TallyGroup).filter(
        TallyGroup.company_id == current_user.company_id,
        TallyGroup.tally_key == key,
        TallyGroup.is_active == True,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Group '{name}' already exists")

    group = TallyGroup(
        company_id=current_user.company_id,
        name=name,
        parent=data.parent or None,
        nature=data.nature or None,
        tally_key=key,
        source="finpilot",
        tally_sync_status="pending",
    )
    db.add(group)
    db.flush()

    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == current_user.company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()

    tally_queued = False
    if connector:
        payload = {"name": name}
        if data.parent and data.parent.strip():
            payload["parent"] = data.parent.strip()
        job = TallyIntegrationJob(
            company_id=current_user.company_id,
            connector_id=connector.id,
            created_by=current_user.id,
            operation=TallyJobOperation.CREATE_GROUP,
            payload=payload,
            idempotency_key=f"create_group::{group.id}",
        )
        db.add(job)
        db.flush()
        group.tally_job_id = job.id
        tally_queued = True

    db.commit()
    db.refresh(group)

    audit_service.log(
        db, current_user.company_id, current_user.id,
        AuditAction.CREATE,
        entity_type="tally_group",
        entity_id=group.id,
        description=f"Created account group: {name}",
    )
    return {
        "id": str(group.id),
        "name": group.name,
        "parent": group.parent,
        "tally_sync_status": group.tally_sync_status,
        "tally_queued": tally_queued,
    }


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    parent: Optional[str] = None
    nature: Optional[str] = None


@router.patch("/groups/{group_id}")
def update_group(
    group_id: str,
    data: GroupUpdate,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    group = db.query(TallyGroup).filter(
        TallyGroup.id == uuid.UUID(group_id),
        TallyGroup.company_id == current_user.company_id,
        TallyGroup.is_active == True,
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    was_synced = group.tally_sync_status == "synced"
    if data.name is not None:
        group.name = data.name.strip()
    if data.parent is not None:
        group.parent = data.parent.strip() or None
    if data.nature is not None:
        group.nature = data.nature.strip() or None
    group.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPDATE,
                      entity_type="tally_group", entity_id=group.id,
                      description=f"Updated group: {group.name}")
    return {
        "id": str(group.id), "name": group.name, "tally_sync_status": group.tally_sync_status,
        "warning": "Already synced to TallyPrime — update it there manually too." if was_synced else None,
    }


@router.delete("/groups/{group_id}")
def delete_group(
    group_id: str,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    group = db.query(TallyGroup).filter(
        TallyGroup.id == uuid.UUID(group_id),
        TallyGroup.company_id == current_user.company_id,
        TallyGroup.is_active == True,
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _cancel_pending_job(db, group.tally_job_id)
    # Groups from Tally sync are system-level — only allow soft-delete for FinPilot-created ones
    if group.source == "tally_sync":
        raise HTTPException(
            status_code=400,
            detail="System groups imported from TallyPrime cannot be deleted from FinPilot. Delete them in TallyPrime directly."
        )
    group.is_active = False
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                      entity_type="tally_group", entity_id=group.id,
                      description=f"Deleted group: {group.name}")
    return {"status": "deleted", "message": "Deleted successfully."}


# ─── Conflict detection ───────────────────────────────────────────────────────

@router.get("/conflicts")
def list_conflicts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all Tally master records currently in CONFLICT state for this company."""
    from app.models.tally_masters import TallyGodown as TallyGodownModel
    cid = current_user.company_id
    conflicts = []

    for model, entity_type in [
        (TallyLedger, "ledger"),
        (TallyStockGroup, "stock_group"),
        (TallyUnit, "unit"),
        (TallyGodownModel, "godown"),
        (TallyGroup, "group"),
    ]:
        records = db.query(model).filter(
            model.company_id == cid,
            model.tally_sync_status == "conflict",
            model.is_active == True,
        ).all()
        for r in records:
            conflicts.append({
                "id": str(r.id),
                "entity_type": entity_type,
                "name": r.name,
                "conflict_data": r.conflict_data,
                "conflict_detected_at": r.conflict_detected_at.isoformat() if r.conflict_detected_at else None,
            })

    return {"conflicts": conflicts, "total": len(conflicts)}


class ConflictResolution(BaseModel):
    entity_type: str   # ledger | stock_group | unit | godown | group
    entity_id: str
    resolution: str    # keep_finpilot | keep_tally


@router.post("/conflicts/resolve")
def resolve_conflict(
    data: ConflictResolution,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    """Resolve a conflict by choosing FinPilot or TallyPrime version."""
    from app.services.conflict_service import resolve_conflict as _resolve
    if data.resolution not in ("keep_finpilot", "keep_tally"):
        raise HTTPException(status_code=422, detail="resolution must be 'keep_finpilot' or 'keep_tally'")
    result = _resolve(db, data.entity_type, data.entity_id, data.resolution, current_user.company_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    audit_service.log(
        db, current_user.company_id, current_user.id, AuditAction.UPDATE,
        entity_type=data.entity_type,
        description=f"Conflict resolved ({data.resolution}) for {data.entity_type} {data.entity_id}",
    )
    return result
