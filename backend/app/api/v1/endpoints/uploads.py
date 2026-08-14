from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.models.upload import Upload, UploadType, UploadStatus
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from app.core.config import settings
import pandas as pd
import io
import os
import uuid
import json
from typing import Optional

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
MAX_SIZE_BYTES = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def validate_file(file: UploadFile) -> None:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")


def read_dataframe(content: bytes, filename: str) -> pd.DataFrame:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".csv":
        return pd.read_csv(io.BytesIO(content))
    return pd.read_excel(io.BytesIO(content))


COLUMN_MAPS = {
    "customers": ["name", "email", "phone", "address", "city", "state", "gst_number", "payment_terms_days"],
    "vendors": ["name", "email", "phone", "address", "city", "state", "gst_number", "payment_terms_days"],
    "products": ["sku", "name", "category", "purchase_price", "selling_price", "tax_rate", "stock_quantity", "reorder_threshold"],
    "expenses": ["title", "category", "expense_date", "amount", "tax_amount", "description"],
}


@router.post("/csv")
async def upload_csv(
    file: UploadFile = File(...),
    upload_type: str = Form(...),
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    validate_file(file)

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=400, detail=f"File too large. Max size: {settings.MAX_UPLOAD_SIZE_MB}MB")

    upload_record = Upload(
        company_id=current_user.company_id,
        uploaded_by=current_user.id,
        filename=f"{uuid.uuid4()}_{file.filename}",
        original_filename=file.filename,
        file_type=os.path.splitext(file.filename or "")[1].lower().strip("."),
        upload_type=UploadType(upload_type) if upload_type in [e.value for e in UploadType] else None,
        status=UploadStatus.PROCESSING,
    )
    db.add(upload_record)
    db.commit()

    try:
        df = read_dataframe(content, file.filename)
        df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

        expected = COLUMN_MAPS.get(upload_type, [])
        missing_cols = [c for c in ["name"] if c not in df.columns and upload_type in ("customers", "vendors")]

        valid_rows = []
        invalid_rows = []
        errors = []

        for idx, row in df.iterrows():
            row_errors = []
            if upload_type in ("customers", "vendors") and not str(row.get("name", "")).strip():
                row_errors.append("Name is required")
            if upload_type == "expenses" and not str(row.get("title", "")).strip():
                row_errors.append("Title is required")
            if upload_type == "products" and not str(row.get("name", "")).strip():
                row_errors.append("Name is required")

            if row_errors:
                invalid_rows.append({"row": idx + 2, "errors": row_errors, "data": row.to_dict()})
            else:
                valid_rows.append(row.to_dict())

        # Commit valid rows
        committed = 0
        if upload_type == "customers":
            from app.models.customer import Customer
            for row in valid_rows:
                c = Customer(
                    company_id=current_user.company_id,
                    name=str(row.get("name", "")).strip(),
                    email=str(row.get("email", "")) if row.get("email") else None,
                    phone=str(row.get("phone", "")) if row.get("phone") else None,
                    address=str(row.get("address", "")) if row.get("address") else None,
                    city=str(row.get("city", "")) if row.get("city") else None,
                    state=str(row.get("state", "")) if row.get("state") else None,
                    gst_number=str(row.get("gst_number", "")) if row.get("gst_number") else None,
                )
                db.add(c)
                committed += 1
        elif upload_type == "vendors":
            from app.models.vendor import Vendor
            for row in valid_rows:
                v = Vendor(
                    company_id=current_user.company_id,
                    name=str(row.get("name", "")).strip(),
                    email=str(row.get("email", "")) if row.get("email") else None,
                    phone=str(row.get("phone", "")) if row.get("phone") else None,
                    gst_number=str(row.get("gst_number", "")) if row.get("gst_number") else None,
                )
                db.add(v)
                committed += 1
        elif upload_type == "products":
            from app.models.product import Product
            for row in valid_rows:
                p = Product(
                    company_id=current_user.company_id,
                    name=str(row.get("name", "")).strip(),
                    sku=str(row.get("sku", "")) if row.get("sku") else None,
                    category=str(row.get("category", "")) if row.get("category") else None,
                    purchase_price=float(row.get("purchase_price", 0) or 0),
                    selling_price=float(row.get("selling_price", 0) or 0),
                    tax_rate=float(row.get("tax_rate", 18) or 18),
                    stock_quantity=float(row.get("stock_quantity", 0) or 0),
                    reorder_threshold=float(row.get("reorder_threshold", 10) or 10),
                )
                db.add(p)
                committed += 1

        db.commit()

        upload_record.status = UploadStatus.COMPLETED if not invalid_rows else UploadStatus.PARTIAL
        upload_record.total_rows = len(df)
        upload_record.valid_rows = len(valid_rows)
        upload_record.invalid_rows = len(invalid_rows)
        upload_record.imported_rows = committed
        upload_record.error_summary = {"errors": invalid_rows[:20]} if invalid_rows else None
        db.commit()

        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.UPLOAD,
                          entity_type="upload", entity_id=upload_record.id,
                          description=f"Uploaded {file.filename}: {committed} {upload_type} imported")

        return {
            "upload_id": str(upload_record.id),
            "total_rows": len(df),
            "valid_rows": len(valid_rows),
            "invalid_rows": len(invalid_rows),
            "imported_rows": committed,
            "status": upload_record.status.value,
            "errors": invalid_rows[:10],
            "columns_detected": list(df.columns),
        }

    except Exception as e:
        upload_record.status = UploadStatus.FAILED
        db.commit()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@router.get("/template/{upload_type}")
def download_template(upload_type: str):
    columns = COLUMN_MAPS.get(upload_type)
    if not columns:
        raise HTTPException(status_code=400, detail="Unknown upload type")

    df = pd.DataFrame(columns=columns)
    buffer = io.BytesIO()
    df.to_csv(buffer, index=False)
    buffer.seek(0)

    from fastapi.responses import StreamingResponse
    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={upload_type}_template.csv"}
    )


@router.get("")
def list_uploads(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uploads = db.query(Upload).filter(
        Upload.company_id == current_user.company_id
    ).order_by(Upload.created_at.desc()).limit(20).all()

    return [
        {
            "id": str(u.id), "original_filename": u.original_filename,
            "upload_type": u.upload_type.value if u.upload_type else None,
            "status": u.status.value, "total_rows": u.total_rows,
            "valid_rows": u.valid_rows, "invalid_rows": u.invalid_rows,
            "imported_rows": u.imported_rows,
            "created_at": u.created_at.isoformat(),
        }
        for u in uploads
    ]
