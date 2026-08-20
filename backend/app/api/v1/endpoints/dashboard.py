from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.base import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.invoice import Invoice, InvoiceType
from app.models.expense import Expense
from app.models.tally_masters import TallyLedger, TallyGroup, TallyStockItem
from app.models.tally_connector import TallyConnector, ConnectorStatus
from app.models.tally_job import TallyIntegrationJob, JobStatus
from app.services.dashboard_service import dashboard_service
from collections import defaultdict
from typing import Optional
from datetime import datetime, timezone, timedelta

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ─── Standard TallyPrime group classification ─────────────────────────────────
_INCOME_GROUPS  = {"Sales Accounts", "Direct Income", "Indirect Income", "Other Income"}
_EXPENSE_GROUPS = {"Purchase Accounts", "Direct Expenses", "Indirect Expenses",
                   "Manufacturing Expenses", "Selling Expenses", "Administrative Expenses"}
_CASH_GROUPS    = {"Cash-in-Hand"}
_BANK_GROUPS    = {"Bank Accounts", "Bank OCC A/c", "Bank OD A/c"}
_DEBTOR_GROUPS  = {"Sundry Debtors"}
_CREDITOR_GROUPS= {"Sundry Creditors"}


def _classify(parent_group: str, group_nature_map: dict) -> str:
    """Return semantic category for a ledger based on its parent group."""
    pg = (parent_group or "").strip()
    nature = (group_nature_map.get(pg) or "").lower()
    if pg in _INCOME_GROUPS   or "income" in nature or "revenue" in nature: return "income"
    if pg in _EXPENSE_GROUPS  or "expense" in nature:                        return "expense"
    if pg in _CASH_GROUPS:                                                    return "cash"
    if pg in _BANK_GROUPS:                                                    return "bank"
    if pg in _DEBTOR_GROUPS:                                                  return "debtor"
    if pg in _CREDITOR_GROUPS:                                                return "creditor"
    if "asset" in nature or "fixed" in nature:                               return "asset"
    if "liab" in nature or "capital" in nature:                              return "liability"
    return "other"


@router.get("/tally-kpi")
def get_tally_kpi(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """All KPIs sourced from TallyPrime synced data only — no local FinPilot data."""
    cid = current_user.company_id

    # ── Load Tally masters ────────────────────────────────────────────────────
    ledgers = db.query(TallyLedger).filter(
        TallyLedger.company_id == cid, TallyLedger.is_active == True,
    ).all()

    groups = db.query(TallyGroup).filter(
        TallyGroup.company_id == cid, TallyGroup.is_active == True,
    ).all()
    group_nature_map = {g.name: g.nature or "" for g in groups}

    stock_items = db.query(TallyStockItem).filter(
        TallyStockItem.company_id == cid, TallyStockItem.is_active == True,
    ).all()

    # ── Classify ledgers ──────────────────────────────────────────────────────
    income_by_group:   dict[str, float] = defaultdict(float)
    expense_by_group:  dict[str, float] = defaultdict(float)
    debtor_list:       list[dict]       = []
    creditor_list:     list[dict]       = []
    cash_total   = 0.0
    bank_total   = 0.0
    asset_total  = 0.0
    liab_total   = 0.0

    for l in ledgers:
        bal = abs(l.closing_balance or 0)
        if bal == 0:
            continue
        cat = _classify(l.parent_group, group_nature_map)
        if   cat == "income":   income_by_group[l.parent_group or "Income"] += bal
        elif cat == "expense":  expense_by_group[l.parent_group or "Expense"] += bal
        elif cat == "debtor":   debtor_list.append({"name": l.name, "amount": round(bal, 2)})
        elif cat == "creditor": creditor_list.append({"name": l.name, "amount": round(bal, 2)})
        elif cat == "cash":     cash_total += bal
        elif cat == "bank":     bank_total += bal
        elif cat == "asset":    asset_total += bal
        elif cat == "liability":liab_total += bal

    total_income  = sum(income_by_group.values())
    total_expense = sum(expense_by_group.values())

    # ── Inventory value ───────────────────────────────────────────────────────
    inventory_value = sum((i.rate or 0) * (i.opening_qty or 0) for i in stock_items)

    # ── Monthly voucher trend (synced invoices + expenses, last 6 months) ────
    six_months_ago = datetime.now(timezone.utc) - timedelta(days=185)
    monthly: dict[str, dict] = defaultdict(lambda: {"income": 0.0, "expenses": 0.0})

    for inv in db.query(Invoice).filter(
        Invoice.company_id == cid,
        Invoice.invoice_date >= six_months_ago,
        Invoice.is_deleted.is_not(True),
    ).all():
        key = inv.invoice_date.strftime("%b %Y")
        if inv.invoice_type == InvoiceType.SALES:
            monthly[key]["income"]   += float(inv.total_amount or 0)
        else:
            monthly[key]["expenses"] += float(inv.total_amount or 0)

    for exp in db.query(Expense).filter(
        Expense.company_id == cid,
        Expense.expense_date >= six_months_ago,
        Expense.is_deleted.is_not(True),
    ).all():
        key = exp.expense_date.strftime("%b %Y")
        monthly[key]["expenses"] += float(exp.amount or 0)

    sorted_months = sorted(monthly.keys(), key=lambda x: datetime.strptime(x, "%b %Y"))
    monthly_trend = [
        {
            "month":    m,
            "income":   round(monthly[m]["income"],   2),
            "expenses": round(monthly[m]["expenses"], 2),
            "profit":   round(monthly[m]["income"] - monthly[m]["expenses"], 2),
        }
        for m in sorted_months
    ]

    # ── Sync status ───────────────────────────────────────────────────────────
    connector = db.query(TallyConnector).filter(
        TallyConnector.company_id == cid,
        TallyConnector.status == ConnectorStatus.ACTIVE,
    ).order_by(TallyConnector.created_at.desc()).first()

    last_sync_job = db.query(TallyIntegrationJob).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.SUCCESS,
    ).order_by(TallyIntegrationJob.completed_at.desc()).first()

    pending_jobs = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status.in_([JobStatus.PENDING, JobStatus.CLAIMED, JobStatus.RUNNING]),
    ).scalar() or 0

    failed_jobs = db.query(func.count(TallyIntegrationJob.id)).filter(
        TallyIntegrationJob.company_id == cid,
        TallyIntegrationJob.status == JobStatus.FAILED,
    ).scalar() or 0

    return {
        "income":   {"total": round(total_income, 2),
                     "by_group": sorted([{"name": k, "amount": round(v, 2)} for k, v in income_by_group.items()],
                                        key=lambda x: x["amount"], reverse=True)[:8]},
        "expenses": {"total": round(total_expense, 2),
                     "by_group": sorted([{"name": k, "amount": round(v, 2)} for k, v in expense_by_group.items()],
                                        key=lambda x: x["amount"], reverse=True)[:8]},
        "net_profit":   round(total_income - total_expense, 2),
        "receivables":  {"total": round(sum(d["amount"] for d in debtor_list),   2),
                         "top":   sorted(debtor_list,   key=lambda x: x["amount"], reverse=True)[:8]},
        "payables":     {"total": round(sum(c["amount"] for c in creditor_list), 2),
                         "top":   sorted(creditor_list, key=lambda x: x["amount"], reverse=True)[:8]},
        "cash_bank":    {"total": round(cash_total + bank_total, 2),
                         "cash":  round(cash_total, 2), "bank": round(bank_total, 2)},
        "assets":       round(asset_total, 2),
        "liabilities":  round(liab_total, 2),
        "inventory":    {"total_value": round(inventory_value, 2), "item_count": len(stock_items)},
        "ledger_count": len(ledgers),
        "monthly_trend": monthly_trend,
        "sync": {
            "connected":    connector is not None,
            "tally_company": connector.tally_company_name if connector else None,
            "last_sync":    last_sync_job.completed_at.isoformat() if last_sync_job and last_sync_job.completed_at else None,
            "pending_jobs": pending_jobs,
            "failed_jobs":  failed_jobs,
        },
    }


@router.get("/tally-analytics")
def get_tally_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Detailed analytics from TallyPrime synced ledger & stock data only — no local FinPilot records."""
    cid = current_user.company_id

    ledgers = db.query(TallyLedger).filter(
        TallyLedger.company_id == cid, TallyLedger.is_active == True,
    ).all()

    groups = db.query(TallyGroup).filter(
        TallyGroup.company_id == cid, TallyGroup.is_active == True,
    ).all()
    group_nature_map = {g.name: g.nature or "" for g in groups}

    stock_items = db.query(TallyStockItem).filter(
        TallyStockItem.company_id == cid, TallyStockItem.is_active == True,
    ).all()

    income_ledgers: list[dict]    = []
    expense_ledgers: list[dict]   = []
    debtor_ledgers: list[dict]    = []
    creditor_ledgers: list[dict]  = []
    cash_ledgers: list[dict]      = []
    bank_ledgers: list[dict]      = []
    asset_ledgers: list[dict]     = []
    liability_ledgers: list[dict] = []

    for l in ledgers:
        bal = abs(l.closing_balance or 0)
        if bal == 0:
            continue
        cat = _classify(l.parent_group, group_nature_map)
        base = {"name": l.name, "group": l.parent_group or "", "balance": round(bal, 2)}
        if   cat == "income":    income_ledgers.append(base)
        elif cat == "expense":   expense_ledgers.append(base)
        elif cat == "debtor":    debtor_ledgers.append({**base, "gstin": l.gstin or "", "state": l.state or ""})
        elif cat == "creditor":  creditor_ledgers.append({**base, "gstin": l.gstin or "", "state": l.state or ""})
        elif cat == "cash":      cash_ledgers.append(base)
        elif cat == "bank":      bank_ledgers.append(base)
        elif cat == "asset":     asset_ledgers.append(base)
        elif cat == "liability": liability_ledgers.append(base)

    # Stock grouped by stock_group
    sg_map: dict[str, dict] = defaultdict(lambda: {"items": 0, "value": 0.0, "qty": 0.0})
    for s in stock_items:
        grp = s.stock_group or "Ungrouped"
        sg_map[grp]["items"] += 1
        sg_map[grp]["value"] += (s.rate or 0) * (s.opening_qty or 0)
        sg_map[grp]["qty"]   += (s.opening_qty or 0)

    stock_by_group = sorted(
        [{"group": k, "items": v["items"], "value": round(v["value"], 2), "qty": round(v["qty"], 2)}
         for k, v in sg_map.items()],
        key=lambda x: x["value"], reverse=True,
    )[:20]

    stock_list = sorted(
        [{"name": s.name,
          "group": s.stock_group or "",
          "category": s.stock_category or "",
          "unit": s.unit or "",
          "rate": round(s.rate or 0, 2),
          "qty":  round(s.opening_qty or 0, 2),
          "value": round((s.rate or 0) * (s.opening_qty or 0), 2)}
         for s in stock_items],
        key=lambda x: x["value"], reverse=True,
    )[:50]

    srt = lambda lst: sorted(lst, key=lambda x: x["balance"], reverse=True)
    return {
        "income_ledgers":    srt(income_ledgers)[:25],
        "expense_ledgers":   srt(expense_ledgers)[:25],
        "debtor_ledgers":    srt(debtor_ledgers),
        "creditor_ledgers":  srt(creditor_ledgers),
        "cash_ledgers":      cash_ledgers,
        "bank_ledgers":      bank_ledgers,
        "asset_ledgers":     srt(asset_ledgers)[:25],
        "liability_ledgers": srt(liability_ledgers)[:25],
        "stock_by_group":    stock_by_group,
        "stock_list":        stock_list,
    }


@router.get("/overview")
def get_overview(
    date_from: Optional[datetime] = Query(None),
    date_to:   Optional[datetime] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_overview(db, current_user.company_id, date_from, date_to)


@router.get("/charts")
def get_charts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dashboard_service.get_charts(db, current_user.company_id)
