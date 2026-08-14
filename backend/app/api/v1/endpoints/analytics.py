from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.base import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.product import Product
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
from typing import Optional
import uuid

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
def get_analytics_overview(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    if not date_from:
        date_from = (now - relativedelta(months=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    if not date_to:
        date_to = now

    company_id = current_user.company_id

    revenue = float(db.query(func.sum(Invoice.total_amount)).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.SALES,
        Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                              InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID]),
        Invoice.invoice_date.between(date_from, date_to),
    ).scalar() or 0)

    expenses = float(db.query(func.sum(Expense.total_amount)).filter(
        Expense.company_id == company_id,
        Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
        Expense.expense_date.between(date_from, date_to),
    ).scalar() or 0)

    net_profit = revenue - expenses
    profit_margin = round(net_profit / revenue * 100, 2) if revenue > 0 else 0

    outstanding_receivables = float(db.query(func.sum(Invoice.total_amount - Invoice.paid_amount)).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.SALES,
        Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                             InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
    ).scalar() or 0)

    outstanding_payables = float(db.query(func.sum(Invoice.total_amount - Invoice.paid_amount)).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.PURCHASE,
        Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]),
    ).scalar() or 0)

    customer_count = db.query(func.count(Customer.id)).filter(
        Customer.company_id == company_id, Customer.is_active == True
    ).scalar() or 0

    vendor_count = db.query(func.count(Vendor.id)).filter(
        Vendor.company_id == company_id, Vendor.is_active == True
    ).scalar() or 0

    return {
        "revenue": revenue, "expenses": expenses, "net_profit": net_profit,
        "profit_margin": profit_margin, "outstanding_receivables": outstanding_receivables,
        "outstanding_payables": outstanding_payables, "customer_count": customer_count,
        "vendor_count": vendor_count,
        "period": {"from": date_from.isoformat(), "to": date_to.isoformat()},
    }


@router.get("/charts")
def get_analytics_charts(
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    if not date_from:
        date_from = (now - relativedelta(months=12)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if not date_to:
        date_to = now

    company_id = current_user.company_id

    # Monthly breakdown
    monthly = []
    cursor = date_from.replace(day=1)
    while cursor <= date_to:
        month_end = cursor + relativedelta(months=1) - timedelta(seconds=1)

        rev = float(db.query(func.sum(Invoice.total_amount)).filter(
            Invoice.company_id == company_id,
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PAID,
                                  InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID]),
            Invoice.invoice_date.between(cursor, month_end),
        ).scalar() or 0)

        exp = float(db.query(func.sum(Expense.total_amount)).filter(
            Expense.company_id == company_id,
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
            Expense.expense_date.between(cursor, month_end),
        ).scalar() or 0)

        monthly.append({
            "month": cursor.strftime("%b %Y"),
            "revenue": rev, "expenses": exp, "profit": rev - exp,
        })
        cursor = cursor + relativedelta(months=1)

    # Expense categories
    categories = db.query(
        Expense.category, func.sum(Expense.total_amount).label("total")
    ).filter(
        Expense.company_id == company_id,
        Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
        Expense.expense_date.between(date_from, date_to),
    ).group_by(Expense.category).order_by(func.sum(Expense.total_amount).desc()).all()

    # Customer revenue
    cust_revenue = db.query(
        Customer.name, func.sum(Invoice.total_amount).label("revenue")
    ).join(Invoice, Invoice.customer_id == Customer.id).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.SALES,
        Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PAID, InvoiceStatus.SENT]),
        Invoice.invoice_date.between(date_from, date_to),
    ).group_by(Customer.id, Customer.name).order_by(func.sum(Invoice.total_amount).desc()).limit(8).all()

    # Invoice status breakdown
    inv_statuses = db.query(
        Invoice.status, func.count(Invoice.id).label("count")
    ).filter(
        Invoice.company_id == company_id,
    ).group_by(Invoice.status).all()

    # Receivables aging
    now_ts = datetime.now(timezone.utc)
    buckets = {"current": 0, "1_30": 0, "31_60": 0, "61_90": 0, "over_90": 0}
    overdue_invs = db.query(Invoice).filter(
        Invoice.company_id == company_id,
        Invoice.invoice_type == InvoiceType.SALES,
        Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
    ).all()
    for inv in overdue_invs:
        outstanding = float(inv.total_amount - inv.paid_amount)
        if not inv.due_date or inv.due_date >= now_ts:
            buckets["current"] += outstanding
        else:
            days = (now_ts - inv.due_date).days
            if days <= 30:
                buckets["1_30"] += outstanding
            elif days <= 60:
                buckets["31_60"] += outstanding
            elif days <= 90:
                buckets["61_90"] += outstanding
            else:
                buckets["over_90"] += outstanding

    return {
        "monthly": monthly,
        "expense_categories": [{"name": r.category or "Other", "value": float(r.total)} for r in categories],
        "customer_revenue": [{"name": r.name, "revenue": float(r.revenue)} for r in cust_revenue],
        "invoice_status": [{"status": r.status.value, "count": r.count} for r in inv_statuses],
        "receivables_aging": [
            {"bucket": "Current", "amount": buckets["current"]},
            {"bucket": "1-30 days", "amount": buckets["1_30"]},
            {"bucket": "31-60 days", "amount": buckets["31_60"]},
            {"bucket": "61-90 days", "amount": buckets["61_90"]},
            {"bucket": "90+ days", "amount": buckets["over_90"]},
        ],
    }
