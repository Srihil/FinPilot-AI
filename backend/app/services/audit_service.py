from sqlalchemy.orm import Session
from app.models.audit_log import AuditLog, AuditAction
from app.models.user import User
import uuid
from typing import Optional
from datetime import datetime


class AuditService:
    def log(
        self,
        db: Session,
        company_id: uuid.UUID,
        user_id: Optional[uuid.UUID],
        action: AuditAction,
        entity_type: Optional[str] = None,
        entity_id: Optional[uuid.UUID] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None,
        status: str = "SUCCESS",
        ip_address: Optional[str] = None,
    ) -> AuditLog:
        log = AuditLog(
            company_id=company_id,
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            extra_data=metadata,
            status=status,
            ip_address=ip_address,
        )
        db.add(log)
        db.commit()
        return log

    def get_all(self, db: Session, company_id: uuid.UUID, page: int = 1, page_size: int = 20,
                action: Optional[str] = None, user_id: Optional[str] = None,
                date_from: Optional[datetime] = None, date_to: Optional[datetime] = None):
        query = db.query(AuditLog).filter(AuditLog.company_id == company_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if user_id:
            query = query.filter(AuditLog.user_id == uuid.UUID(user_id))
        if date_from:
            query = query.filter(AuditLog.created_at >= date_from)
        if date_to:
            query = query.filter(AuditLog.created_at <= date_to)

        total = query.count()
        items = query.order_by(AuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return items, total


audit_service = AuditService()
