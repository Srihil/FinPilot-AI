from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_approver
from app.models.user import User
from app.models.approval import Approval, ApprovalStatus, ApprovalEntityType
from app.models.invoice import Invoice
from app.models.expense import Expense, ExpenseStatus
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from pydantic import BaseModel
from datetime import datetime, timezone
from typing import Optional
import uuid

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ApprovalAction(BaseModel):
    notes: Optional[str] = None


@router.get("")
def list_approvals(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Approval).filter(Approval.company_id == current_user.company_id)
    if status:
        query = query.filter(Approval.status == status)
    else:
        query = query.filter(Approval.status == ApprovalStatus.PENDING)

    approvals = query.order_by(Approval.requested_at.desc()).limit(50).all()

    result = []
    for a in approvals:
        item = {
            "id": str(a.id),
            "entity_type": a.entity_type.value,
            "status": a.status.value,
            "requested_at": a.requested_at.isoformat(),
            "review_notes": a.review_notes,
        }

        # Fetch entity details
        if a.entity_type == ApprovalEntityType.INVOICE and a.invoice_id:
            inv = db.query(Invoice).filter(Invoice.id == a.invoice_id).first()
            if inv:
                item.update({
                    "entity_id": str(inv.id),
                    "invoice_number": inv.invoice_number,
                    "amount": float(inv.total_amount),
                    "description": f"Invoice {inv.invoice_number}",
                    "type": inv.invoice_type.value,
                })
        elif a.entity_type == ApprovalEntityType.EXPENSE and a.expense_id:
            exp = db.query(Expense).filter(Expense.id == a.expense_id).first()
            if exp:
                item.update({
                    "entity_id": str(exp.id),
                    "amount": float(exp.total_amount),
                    "description": exp.title,
                    "category": exp.category,
                    "type": "expense",
                })
        elif a.entity_type == ApprovalEntityType.AI_TRANSACTION and a.proposed_data:
            item.update({
                "proposed_data": a.proposed_data,
                "ai_prompt": a.ai_prompt,
                "description": a.ai_prompt or "AI-proposed transaction",
                "amount": a.proposed_data.get("amount", 0),
                "type": a.proposed_data.get("transaction_type", "unknown"),
            })

        # Requester info
        from app.models.user import User as UserModel
        requester = db.query(UserModel).filter(UserModel.id == a.requested_by).first()
        item["requested_by_name"] = requester.full_name if requester else "Unknown"

        result.append(item)

    return {"items": result, "total": len(result)}


@router.post("/{approval_id}/approve")
def approve(
    approval_id: str,
    action: ApprovalAction,
    current_user: User = Depends(require_approver),
    db: Session = Depends(get_db),
):
    a = db.query(Approval).filter(
        Approval.id == uuid.UUID(approval_id),
        Approval.company_id == current_user.company_id,
        Approval.status == ApprovalStatus.PENDING,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found or already processed")

    a.status = ApprovalStatus.APPROVED
    a.reviewed_by = current_user.id
    a.reviewed_at = datetime.now(timezone.utc)
    a.review_notes = action.notes

    # Update the underlying entity
    if a.entity_type == ApprovalEntityType.INVOICE and a.invoice_id:
        inv = db.query(Invoice).filter(Invoice.id == a.invoice_id).first()
        if inv:
            from app.models.invoice import InvoiceStatus
            inv.status = InvoiceStatus.APPROVED
            inv.approved_by = current_user.id
            inv.approved_at = datetime.now(timezone.utc)
            audit_service.log(db, current_user.company_id, current_user.id, AuditAction.APPROVE,
                              entity_type="invoice", entity_id=inv.id,
                              description=f"Invoice {inv.invoice_number} approved")
    elif a.entity_type == ApprovalEntityType.EXPENSE and a.expense_id:
        exp = db.query(Expense).filter(Expense.id == a.expense_id).first()
        if exp:
            exp.status = ExpenseStatus.APPROVED
            exp.approved_by = current_user.id
            exp.approved_at = datetime.now(timezone.utc)
            audit_service.log(db, current_user.company_id, current_user.id, AuditAction.APPROVE,
                              entity_type="expense", entity_id=exp.id,
                              description=f"Expense '{exp.title}' approved")

    db.commit()
    return {"message": "Approved successfully", "approval_id": approval_id}


@router.post("/{approval_id}/reject")
def reject(
    approval_id: str,
    action: ApprovalAction,
    current_user: User = Depends(require_approver),
    db: Session = Depends(get_db),
):
    a = db.query(Approval).filter(
        Approval.id == uuid.UUID(approval_id),
        Approval.company_id == current_user.company_id,
        Approval.status == ApprovalStatus.PENDING,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Approval not found or already processed")

    a.status = ApprovalStatus.REJECTED
    a.reviewed_by = current_user.id
    a.reviewed_at = datetime.now(timezone.utc)
    a.review_notes = action.notes

    if a.entity_type == ApprovalEntityType.INVOICE and a.invoice_id:
        inv = db.query(Invoice).filter(Invoice.id == a.invoice_id).first()
        if inv:
            from app.models.invoice import InvoiceStatus
            inv.status = InvoiceStatus.CANCELLED

    elif a.entity_type == ApprovalEntityType.EXPENSE and a.expense_id:
        exp = db.query(Expense).filter(Expense.id == a.expense_id).first()
        if exp:
            exp.status = ExpenseStatus.REJECTED

    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.REJECT,
                      entity_type="approval", entity_id=a.id,
                      description=f"Approval rejected: {action.notes or 'No reason provided'}")
    return {"message": "Rejected", "approval_id": approval_id}
