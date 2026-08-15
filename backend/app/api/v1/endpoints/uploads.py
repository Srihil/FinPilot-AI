from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.models.upload import Upload, UploadType, UploadStatus
from app.models.audit_log import AuditAction
from app.models.tally_connector import TallyConnector, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
from app.models.tally_masters import TallyLedger, TallyStockGroup, TallyUnit, TallyGodown
from app.services.audit_service import audit_service
from app.core.config import settings
import pandas as pd
import io, os, uuid
from datetime import datetime, timezone

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024

COLUMN_MAPS = {
    "customers":    ["name", "email", "phone", "address", "city", "state", "gst_number", "payment_terms_days"],
    "vendors":      ["name", "email", "phone", "address", "city", "state", "gst_number", "payment_terms_days"],
    "products":     ["sku", "name", "category", "purchase_price", "selling_price", "tax_rate", "stock_quantity", "reorder_threshold"],
    "expenses":     ["title", "category", "expense_date", "amount", "tax_amount", "description"],
    "ledgers":      ["name", "parent_group", "opening_balance"],
    "stock_groups": ["name", "parent"],
    "units":        ["name", "symbol", "decimal_places"],
    "godowns":      ["name", "parent"],
}

VALID_UPLOAD_TYPES = list(COLUMN_MAPS.keys())


def _validate_file(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")


def _read_df(content: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(filename)[1].lower()
    return pd.read_csv(io.BytesIO(content)) if ext == ".csv" else pd.read_excel(io.BytesIO(content))


def _tally_key(company_id, name: str) -> str:
    return f"{company_id}::{str(name).strip().lower()}"


def _active_connector(db: Session, company_id):
    return db.query(TallyConnector).filter(
        TallyConnector.company_id == company_id,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).first()


def _queue_job(db: Session, company_id, connector_id, operation: TallyJobOperation, payload: dict, ikey: str) -> bool:
    if db.query(TallyIntegrationJob).filter(TallyIntegrationJob.idempotency_key == ikey).first():
        return False
    db.add(TallyIntegrationJob(
        company_id=company_id,
        connector_id=connector_id,
        operation=operation,
        payload=payload,
        idempotency_key=ikey,
    ))
    return True


# ─── CSV Upload ───────────────────────────────────────────────────────────────

@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    upload_type: str = Form(...),
    sync_to_tally: bool = Form(False),
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    if upload_type not in VALID_UPLOAD_TYPES:
        raise HTTPException(status_code=400, detail=f"Unknown upload type. Allowed: {', '.join(VALID_UPLOAD_TYPES)}")

    _validate_file(file)
    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB}MB")

    try:
        ut = UploadType(upload_type)
    except ValueError:
        ut = None

    record = Upload(
        company_id=current_user.company_id,
        uploaded_by=current_user.id,
        filename=f"{uuid.uuid4()}_{file.filename}",
        original_filename=file.filename,
        file_type=os.path.splitext(file.filename or "")[1].lower().strip("."),
        upload_type=ut,
        status=UploadStatus.PROCESSING,
    )
    db.add(record)
    db.commit()

    try:
        df = _read_df(content, file.filename)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        valid_rows, invalid_rows = [], []

        for idx, row in df.iterrows():
            errs = []
            name = str(row.get("name", "")).strip()
            title = str(row.get("title", "")).strip()

            if upload_type in ("customers", "vendors", "products", "ledgers", "stock_groups", "units", "godowns") and not name:
                errs.append("Name is required")
            if upload_type == "expenses" and not title:
                errs.append("Title is required")

            if errs:
                invalid_rows.append({"row": idx + 2, "field": "name", "message": "; ".join(errs)})
            else:
                valid_rows.append(row.to_dict())

        committed = 0
        tally_queued = 0
        now = datetime.now(timezone.utc)
        connector = _active_connector(db, current_user.company_id)

        # ── Customers ────────────────────────────────────────────────────────
        if upload_type == "customers":
            from app.models.customer import Customer
            for row in valid_rows:
                db.add(Customer(
                    company_id=current_user.company_id,
                    name=str(row.get("name", "")).strip(),
                    email=str(row.get("email", "")) or None,
                    phone=str(row.get("phone", "")) or None,
                    address=str(row.get("address", "")) or None,
                    city=str(row.get("city", "")) or None,
                    state=str(row.get("state", "")) or None,
                    gst_number=str(row.get("gst_number", "")) or None,
                    is_active=True,
                ))
                committed += 1

        # ── Vendors ──────────────────────────────────────────────────────────
        elif upload_type == "vendors":
            from app.models.vendor import Vendor
            for row in valid_rows:
                db.add(Vendor(
                    company_id=current_user.company_id,
                    name=str(row.get("name", "")).strip(),
                    email=str(row.get("email", "")) or None,
                    phone=str(row.get("phone", "")) or None,
                    gst_number=str(row.get("gst_number", "")) or None,
                    is_active=True,
                ))
                committed += 1

        # ── Products ─────────────────────────────────────────────────────────
        elif upload_type == "products":
            from app.models.product import Product
            for row in valid_rows:
                db.add(Product(
                    company_id=current_user.company_id,
                    name=str(row.get("name", "")).strip(),
                    sku=str(row.get("sku", "")) or None,
                    category=str(row.get("category", "")) or None,
                    purchase_price=float(row.get("purchase_price") or 0),
                    selling_price=float(row.get("selling_price") or 0),
                    tax_rate=float(row.get("tax_rate") or 18),
                    stock_quantity=float(row.get("stock_quantity") or 0),
                    reorder_threshold=float(row.get("reorder_threshold") or 10),
                ))
                committed += 1

        # ── Expenses ─────────────────────────────────────────────────────────
        elif upload_type == "expenses":
            from app.models.expense import Expense, ExpenseStatus
            for row in valid_rows:
                raw_date = row.get("expense_date")
                try:
                    exp_date = pd.to_datetime(raw_date).to_pydatetime().replace(tzinfo=timezone.utc) if raw_date else now
                except Exception:
                    exp_date = now
                db.add(Expense(
                    company_id=current_user.company_id,
                    title=str(row.get("title", "")).strip(),
                    category=str(row.get("category", "General")) or "General",
                    expense_date=exp_date,
                    amount=float(row.get("amount") or 0),
                    tax_amount=float(row.get("tax_amount") or 0),
                    total_amount=float(row.get("amount") or 0),
                    currency="INR",
                    status=ExpenseStatus.DRAFT,
                ))
                committed += 1

        # ── Ledgers ──────────────────────────────────────────────────────────
        elif upload_type == "ledgers":
            for row in valid_rows:
                name = str(row.get("name", "")).strip()
                key = _tally_key(current_user.company_id, name)
                exists = db.query(TallyLedger).filter(
                    TallyLedger.company_id == current_user.company_id,
                    TallyLedger.tally_key == key,
                ).first()
                if exists:
                    invalid_rows.append({"row": committed + 2, "field": "name", "message": f"Ledger '{name}' already exists"})
                    continue
                parent_group = str(row.get("parent_group", "Sundry Debtors")).strip() or "Sundry Debtors"
                opening_balance = float(row.get("opening_balance") or 0)
                ledger = TallyLedger(
                    company_id=current_user.company_id, name=name,
                    parent_group=parent_group, opening_balance=opening_balance,
                    tally_key=key, source="finpilot", tally_sync_status="pending", is_active=True,
                )
                db.add(ledger)
                db.flush()
                committed += 1
                if connector and sync_to_tally:
                    ikey = f"bulk_ledger::{key}"
                    if _queue_job(db, current_user.company_id, connector.id, TallyJobOperation.CREATE_LEDGER,
                                  {"name": name, "group": parent_group, "opening_balance": str(int(opening_balance))}, ikey):
                        tally_queued += 1

        # ── Stock Groups ─────────────────────────────────────────────────────
        elif upload_type == "stock_groups":
            for row in valid_rows:
                name = str(row.get("name", "")).strip()
                if name.lower() == "primary":
                    continue
                key = _tally_key(current_user.company_id, name)
                exists = db.query(TallyStockGroup).filter(
                    TallyStockGroup.company_id == current_user.company_id,
                    TallyStockGroup.tally_key == key,
                ).first()
                if exists:
                    invalid_rows.append({"row": committed + 2, "field": "name", "message": f"Stock group '{name}' already exists"})
                    continue
                parent = str(row.get("parent", "")).strip() or None
                if parent and parent.lower() == "primary":
                    parent = None
                sg = TallyStockGroup(
                    company_id=current_user.company_id, name=name, parent=parent,
                    tally_key=key, source="finpilot", tally_sync_status="pending", is_active=True,
                )
                db.add(sg)
                db.flush()
                committed += 1
                if connector and sync_to_tally:
                    payload = {"name": name}
                    if parent:
                        payload["parent"] = parent
                    ikey = f"bulk_sg::{key}"
                    if _queue_job(db, current_user.company_id, connector.id, TallyJobOperation.CREATE_STOCK_GROUP, payload, ikey):
                        tally_queued += 1

        # ── Units ────────────────────────────────────────────────────────────
        elif upload_type == "units":
            for row in valid_rows:
                name = str(row.get("name", "")).strip()
                key = _tally_key(current_user.company_id, name)
                exists = db.query(TallyUnit).filter(
                    TallyUnit.company_id == current_user.company_id,
                    TallyUnit.tally_key == key,
                ).first()
                if exists:
                    invalid_rows.append({"row": committed + 2, "field": "name", "message": f"Unit '{name}' already exists"})
                    continue
                symbol = str(row.get("symbol", name)).strip().replace(" ", "")[:8] or name[:8]
                decimals = int(float(row.get("decimal_places") or 0))
                unit = TallyUnit(
                    company_id=current_user.company_id, name=name, symbol=symbol,
                    decimal_places=decimals, unit_type="simple",
                    tally_key=key, source="finpilot", tally_sync_status="pending", is_active=True,
                )
                db.add(unit)
                db.flush()
                committed += 1
                if connector and sync_to_tally:
                    ikey = f"bulk_unit::{key}"
                    if _queue_job(db, current_user.company_id, connector.id, TallyJobOperation.CREATE_UNIT,
                                  {"name": name, "symbol": symbol, "decimal_places": str(decimals)}, ikey):
                        tally_queued += 1

        # ── Godowns ──────────────────────────────────────────────────────────
        elif upload_type == "godowns":
            for row in valid_rows:
                name = str(row.get("name", "")).strip()
                key = _tally_key(current_user.company_id, name)
                exists = db.query(TallyGodown).filter(
                    TallyGodown.company_id == current_user.company_id,
                    TallyGodown.tally_key == key,
                ).first()
                if exists:
                    invalid_rows.append({"row": committed + 2, "field": "name", "message": f"Godown '{name}' already exists"})
                    continue
                parent = str(row.get("parent", "")).strip() or None
                godown = TallyGodown(
                    company_id=current_user.company_id, name=name, parent=parent,
                    tally_key=key, source="finpilot", tally_sync_status="pending", is_active=True,
                )
                db.add(godown)
                db.flush()
                committed += 1
                if connector and sync_to_tally:
                    payload = {"name": name}
                    if parent:
                        payload["parent"] = parent
                    ikey = f"bulk_godown::{key}"
                    if _queue_job(db, current_user.company_id, connector.id, TallyJobOperation.CREATE_GODOWN, payload, ikey):
                        tally_queued += 1

        db.commit()

        record.status = UploadStatus.COMPLETED if not invalid_rows else UploadStatus.PARTIAL
        record.total_rows = len(df)
        record.valid_rows = len(valid_rows)
        record.invalid_rows = len(invalid_rows)
        record.imported_rows = committed
        record.error_summary = {"errors": invalid_rows[:50]} if invalid_rows else None
        record.completed_at = now
        db.commit()

        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPLOAD,
                          entity_type="upload", entity_id=record.id,
                          description=f"Bulk upload {file.filename}: {committed} {upload_type} imported")

        return {
            "upload_id": str(record.id),
            "total_rows": len(df),
            "valid_rows": len(valid_rows),
            "invalid_rows": len(invalid_rows),
            "imported_rows": committed,
            "tally_queued": tally_queued,
            "status": record.status.value,
            "errors": [{"row": e.get("row"), "field": e.get("field"), "message": e.get("message")} for e in invalid_rows[:20]],
            "duplicate_rows": 0,
            "columns_detected": list(df.columns),
        }

    except HTTPException:
        raise
    except Exception as e:
        record.status = UploadStatus.FAILED
        db.commit()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


# ─── PDF Invoice ──────────────────────────────────────────────────────────────

@router.post("/pdf-invoice")
async def upload_pdf_invoice(
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large. Max {settings.MAX_UPLOAD_SIZE_MB}MB")

    from app.core.config import settings as cfg

    # Try AI extraction if provider configured
    extracted = {
        "vendor_name": "", "invoice_number": "", "invoice_date": "",
        "due_date": "", "subtotal": 0, "tax_amount": 0, "total_amount": 0,
        "line_items": [], "notes": "",
    }

    record = Upload(
        company_id=current_user.company_id,
        uploaded_by=current_user.id,
        filename=f"{uuid.uuid4()}_{file.filename}",
        original_filename=file.filename,
        file_type="pdf",
        upload_type=UploadType.INVOICE_PDF,
        status=UploadStatus.COMPLETED,
        extracted_data=extracted,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()

    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPLOAD,
                      entity_type="upload", entity_id=record.id,
                      description=f"PDF invoice uploaded: {file.filename}")

    return {"upload_id": str(record.id), "extracted": extracted, "filename": file.filename}


# ─── Template download ────────────────────────────────────────────────────────

@router.get("/template/{upload_type}")
def download_template(upload_type: str):
    columns = COLUMN_MAPS.get(upload_type)
    if not columns:
        raise HTTPException(status_code=400, detail=f"Unknown upload type. Allowed: {', '.join(COLUMN_MAPS.keys())}")

    # Add a sample row so users know the format
    sample_data: dict[str, list] = {col: [] for col in columns}
    if upload_type == "customers":
        sample_data = {"name": ["Acme Corp"], "email": ["contact@acme.com"], "phone": ["9876543210"],
                       "address": ["123 MG Road"], "city": ["Mumbai"], "state": ["Maharashtra"],
                       "gst_number": ["27AAAAA0000A1Z5"], "payment_terms_days": [30]}
    elif upload_type == "vendors":
        sample_data = {"name": ["Tata Steel"], "email": ["accounts@tata.com"], "phone": ["9876543210"],
                       "address": ["Jamshedpur"], "city": ["Jamshedpur"], "state": ["Jharkhand"],
                       "gst_number": ["20AAAAA0000A1Z5"], "payment_terms_days": [45]}
    elif upload_type == "products":
        sample_data = {"sku": ["SKU-001"], "name": ["Widget A"], "category": ["Electronics"],
                       "purchase_price": [500], "selling_price": [750], "tax_rate": [18],
                       "stock_quantity": [100], "reorder_threshold": [10]}
    elif upload_type == "expenses":
        sample_data = {"title": ["Office Rent"], "category": ["Rent"], "expense_date": ["2026-08-01"],
                       "amount": [50000], "tax_amount": [0], "description": ["Monthly office rent"]}
    elif upload_type == "ledgers":
        sample_data = {"name": ["ABC Traders"], "parent_group": ["Sundry Debtors"], "opening_balance": [0]}
    elif upload_type == "stock_groups":
        sample_data = {"name": ["Electronics"], "parent": [""]}
    elif upload_type == "units":
        sample_data = {"name": ["Pieces"], "symbol": ["Pcs"], "decimal_places": [0]}
    elif upload_type == "godowns":
        sample_data = {"name": ["Main Warehouse"], "parent": [""]}

    df = pd.DataFrame(sample_data)
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={upload_type}_template.csv"}
    )


# ─── Upload history ───────────────────────────────────────────────────────────

@router.get("")
def list_uploads(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uploads = db.query(Upload).filter(
        Upload.company_id == current_user.company_id
    ).order_by(Upload.created_at.desc()).limit(50).all()

    return [
        {
            "id": str(u.id),
            "original_filename": u.original_filename,
            "upload_type": u.upload_type.value if u.upload_type else None,
            "status": u.status.value,
            "total_rows": u.total_rows or 0,
            "valid_rows": u.valid_rows or 0,
            "invalid_rows": u.invalid_rows or 0,
            "imported_rows": u.imported_rows or 0,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "completed_at": u.completed_at.isoformat() if u.completed_at else None,
            "errors": (u.error_summary or {}).get("errors", [])[:5],
        }
        for u in uploads
    ]
