from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.services.audit_service import audit_service
from typing import Optional
from datetime import datetime
import math

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


@router.get("")
def list_audit_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    items, total = audit_service.get_all(
        db, current_user.company_id, page, page_size, action, user_id, date_from, date_to
    )

    return {
        "items": [
            {
                "id": str(log.id),
                "action": log.action.value,
                "entity_type": log.entity_type,
                "entity_id": str(log.entity_id) if log.entity_id else None,
                "description": log.description,
                "status": log.status,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat(),
                "user_id": str(log.user_id) if log.user_id else None,
                "user_name": log.user.full_name if log.user else "System",
            }
            for log in items
        ],
        "total": total, "page": page, "page_size": page_size,
        "total_pages": math.ceil(total / page_size),
    }
