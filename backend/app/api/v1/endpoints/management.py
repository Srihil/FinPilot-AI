"""
Management endpoints — unified overview, Tally master management, and voucher management.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, require_admin_or_accountant, require_admin
from app.db.base import get_db
from app.models.audit_log import AuditAction
from app.models.customer import Customer
from app.models.expense import Expense
from app.models.invoice import Invoice, InvoiceType
from app.models.payment import Payment
from app.models.product import Product
from app.models.tally_connector import TallyConnector, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, JobStatus, TallyJobOperation
from app.models.tally_masters import TallyGodown, TallyLedger, TallyStockGroup, TallyUnit
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
    page_size: int = Query(20, ge=1, le=100),
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
        ikey = f"create_ledger::{key}"
        existing_job = db.query(TallyIntegrationJob).filter(
            TallyIntegrationJob.idempotency_key == ikey
        ).first()
        if not existing_job:
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

    was_synced = ledger.tally_sync_status == "synced"
    _cancel_pending_job(db, ledger.tally_job_id)
    ledger.is_active = False
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                      entity_type="tally_ledger", entity_id=ledger.id,
                      description=f"Deleted ledger: {ledger.name}")
    return {
        "deleted": True, "was_synced": was_synced,
        "message": "Deleted from FinPilot. This ledger still exists in TallyPrime — remove it there manually." if was_synced else "Deleted successfully.",
    }


# ─── Stock Group management ──────────────────────────────────────────────────────

class StockGroupCreate(BaseModel):
    name: str
    parent: Optional[str] = None  # None = root (do NOT send "Primary")


@router.get("/stock-groups")
def list_stock_groups(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(TallyStockGroup).filter(
        TallyStockGroup.company_id == current_user.company_id,
        TallyStockGroup.is_active == True,
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
        ikey = f"create_stock_group::{key}"
        if not db.query(TallyIntegrationJob).filter(TallyIntegrationJob.idempotency_key == ikey).first():
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
                idempotency_key=ikey,
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
    was_synced = sg.tally_sync_status == "synced"
    _cancel_pending_job(db, sg.tally_job_id)
    sg.is_active = False
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                      entity_type="tally_stock_group", entity_id=sg.id,
                      description=f"Deleted stock group: {sg.name}")
    return {
        "deleted": True, "was_synced": was_synced,
        "message": "Deleted from FinPilot. This stock group still exists in TallyPrime — remove it there manually." if was_synced else "Deleted successfully.",
    }


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
    page_size: int = Query(20, ge=1, le=100),
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
        ikey = f"create_unit::{key}"
        if not db.query(TallyIntegrationJob).filter(TallyIntegrationJob.idempotency_key == ikey).first():
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
                idempotency_key=ikey,
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
    was_synced = unit.tally_sync_status == "synced"
    _cancel_pending_job(db, unit.tally_job_id)
    unit.is_active = False
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                      entity_type="tally_unit", entity_id=unit.id,
                      description=f"Deleted unit: {unit.name}")
    return {
        "deleted": True, "was_synced": was_synced,
        "message": "Deleted from FinPilot. This unit still exists in TallyPrime — remove it there manually." if was_synced else "Deleted successfully.",
    }


# ─── Godown management ──────────────────────────────────────────────────────────

class GodownCreate(BaseModel):
    name: str
    parent: Optional[str] = None  # None = root location


@router.get("/godowns")
def list_godowns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
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
        ikey = f"create_godown::{key}"
        if not db.query(TallyIntegrationJob).filter(TallyIntegrationJob.idempotency_key == ikey).first():
            payload = {"name": name}
            if data.parent and data.parent.strip():
                payload["parent"] = data.parent.strip()
            job = TallyIntegrationJob(
                company_id=current_user.company_id,
                connector_id=connector.id,
                created_by=current_user.id,
                operation=TallyJobOperation.CREATE_GODOWN,
                payload=payload,
                idempotency_key=ikey,
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
    was_synced = godown.tally_sync_status == "synced"
    _cancel_pending_job(db, godown.tally_job_id)
    godown.is_active = False
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.DELETE,
                      entity_type="tally_godown", entity_id=godown.id,
                      description=f"Deleted godown: {godown.name}")
    return {
        "deleted": True, "was_synced": was_synced,
        "message": "Deleted from FinPilot. This godown still exists in TallyPrime — remove it there manually." if was_synced else "Deleted successfully.",
    }


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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    cid = current_user.company_id
    results = []

    # ── Invoices (SALES / PURCHASE) ──────────────────────────────────────────
    vt = (voucher_type or "").upper()
    include_invoices = vt in ("", "ALL", "SALES", "PURCHASE")
    include_expenses = vt in ("", "ALL", "EXPENSE", "PURCHASE")
    include_payments = vt in ("", "ALL", "PAYMENT", "RECEIPT")

    if include_invoices:
        inv_q = db.query(Invoice).filter(Invoice.company_id == cid)
        if vt == "SALES":
            inv_q = inv_q.filter(Invoice.invoice_type == InvoiceType.SALES)
        elif vt == "PURCHASE":
            inv_q = inv_q.filter(Invoice.invoice_type == InvoiceType.PURCHASE)
        if search:
            inv_q = inv_q.filter(
                or_(Invoice.invoice_number.ilike(f"%{search}%"))
            )
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
            results.append({
                "id": str(inv.id),
                "voucher_number": inv.invoice_number,
                "date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "voucher_type": inv.invoice_type.value if inv.invoice_type else "INVOICE",
                "party": inv.customer_id and str(inv.customer_id),
                "amount": float(inv.total_amount or 0),
                "status": inv.status.value if inv.status else "DRAFT",
                "source": "finpilot",
                "tally_sync_status": "synced" if getattr(inv, "tally_synced", False) else "pending",
                "created_at": inv.created_at.isoformat() if inv.created_at else None,
                "entity_type": "invoice",
            })

    if include_expenses:
        exp_q = db.query(Expense).filter(Expense.company_id == cid)
        if search:
            exp_q = exp_q.filter(Expense.title.ilike(f"%{search}%"))
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

        for exp in exp_q.all():
            results.append({
                "id": str(exp.id),
                "voucher_number": getattr(exp, "ref_number", None) or f"EXP-{str(exp.id)[:8].upper()}",
                "date": exp.expense_date.isoformat() if exp.expense_date else None,
                "voucher_type": "EXPENSE",
                "party": None,
                "amount": float(exp.amount or 0),
                "status": exp.status.value if exp.status else "DRAFT",
                "source": "finpilot",
                "tally_sync_status": "pending",
                "created_at": exp.created_at.isoformat() if exp.created_at else None,
                "entity_type": "expense",
                "title": exp.title,
            })

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
