"""
Controlled Finance Tools - these are the ONLY ways the AI can access financial data.
The LLM calls these tools; the tools run deterministic database queries.
No arbitrary SQL is ever executed.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus
from app.models.payment import Payment
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.inventory import InventoryTransaction
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import uuid


class PeriodInput(BaseModel):
    company_id: str
    date_from: Optional[str] = None  # ISO format
    date_to: Optional[str] = None


class CustomerInput(BaseModel):
    company_id: str
    customer_id: Optional[str] = None


class TopNInput(BaseModel):
    company_id: str
    n: int = 5
    date_from: Optional[str] = None
    date_to: Optional[str] = None


def _parse_date(s: Optional[str], default: datetime) -> datetime:
    if not s:
        return default
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return default


def _default_period():
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now


class FinanceTools:
    def __init__(self, db: Session):
        self.db = db

    def get_total_revenue(self, company_id: str, date_from: str = None, date_to: str = None) -> dict:
        df_default, dt_default = _default_period()
        df = _parse_date(date_from, df_default)
        dt = _parse_date(date_to, dt_default)

        revenue = float(self.db.query(func.sum(Invoice.total_amount)).filter(
            Invoice.company_id == uuid.UUID(company_id),
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                                  InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID]),
            Invoice.invoice_date >= df,
            Invoice.invoice_date <= dt,
        ).scalar() or 0)

        return {
            "total_revenue": revenue,
            "period": f"{df.strftime('%d %b %Y')} to {dt.strftime('%d %b %Y')}",
            "currency": "INR",
        }

    def get_total_expenses(self, company_id: str, date_from: str = None, date_to: str = None) -> dict:
        df_default, dt_default = _default_period()
        df = _parse_date(date_from, df_default)
        dt = _parse_date(date_to, dt_default)

        expenses = float(self.db.query(func.sum(Expense.total_amount)).filter(
            Expense.company_id == uuid.UUID(company_id),
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
            Expense.expense_date >= df,
            Expense.expense_date <= dt,
        ).scalar() or 0)

        return {
            "total_expenses": expenses,
            "period": f"{df.strftime('%d %b %Y')} to {dt.strftime('%d %b %Y')}",
            "currency": "INR",
        }

    def get_net_profit(self, company_id: str, date_from: str = None, date_to: str = None) -> dict:
        rev = self.get_total_revenue(company_id, date_from, date_to)
        exp = self.get_total_expenses(company_id, date_from, date_to)
        profit = rev["total_revenue"] - exp["total_expenses"]
        margin = (profit / rev["total_revenue"] * 100) if rev["total_revenue"] > 0 else 0
        return {
            "net_profit": profit,
            "total_revenue": rev["total_revenue"],
            "total_expenses": exp["total_expenses"],
            "profit_margin_percent": round(margin, 2),
            "period": rev["period"],
            "currency": "INR",
        }

    def get_top_customers(self, company_id: str, n: int = 5, date_from: str = None, date_to: str = None) -> dict:
        df_default, dt_default = _default_period()
        df = _parse_date(date_from, df_default)
        dt = _parse_date(date_to, dt_default)

        results = self.db.query(
            Customer.id, Customer.name,
            func.sum(Invoice.total_amount).label("revenue"),
            func.count(Invoice.id).label("invoice_count"),
        ).join(Invoice, Invoice.customer_id == Customer.id).filter(
            Invoice.company_id == uuid.UUID(company_id),
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                                  InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID]),
            Invoice.invoice_date >= df,
            Invoice.invoice_date <= dt,
        ).group_by(Customer.id, Customer.name).order_by(func.sum(Invoice.total_amount).desc()).limit(n).all()

        return {
            "top_customers": [
                {"rank": i + 1, "name": r.name, "revenue": float(r.revenue), "invoice_count": r.invoice_count}
                for i, r in enumerate(results)
            ],
            "period": f"{df.strftime('%d %b %Y')} to {dt.strftime('%d %b %Y')}",
            "currency": "INR",
        }

    def get_customer_outstanding(self, company_id: str) -> dict:
        results = self.db.query(
            Customer.name,
            func.sum(Invoice.total_amount - Invoice.paid_amount).label("outstanding"),
        ).join(Invoice, Invoice.customer_id == Customer.id).filter(
            Invoice.company_id == uuid.UUID(company_id),
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                                  InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
        ).group_by(Customer.id, Customer.name).having(
            func.sum(Invoice.total_amount - Invoice.paid_amount) > 0
        ).order_by(func.sum(Invoice.total_amount - Invoice.paid_amount).desc()).all()

        total = sum(float(r.outstanding) for r in results)
        return {
            "customers_with_outstanding": [
                {"name": r.name, "outstanding": float(r.outstanding)}
                for r in results
            ],
            "total_outstanding": total,
            "currency": "INR",
        }

    def get_overdue_invoices(self, company_id: str) -> dict:
        now = datetime.now(timezone.utc)
        invoices = self.db.query(Invoice).filter(
            Invoice.company_id == uuid.UUID(company_id),
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.status.in_([InvoiceStatus.SENT, InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.OVERDUE]),
            Invoice.due_date < now,
            Invoice.due_date.isnot(None),
        ).order_by(Invoice.due_date).all()

        return {
            "overdue_invoices": [
                {
                    "invoice_number": inv.invoice_number,
                    "amount": float(inv.total_amount),
                    "outstanding": float(inv.total_amount - inv.paid_amount),
                    "due_date": inv.due_date.strftime("%d %b %Y"),
                    "days_overdue": (now - inv.due_date).days,
                }
                for inv in invoices
            ],
            "total_overdue": sum(float(inv.total_amount - inv.paid_amount) for inv in invoices),
            "count": len(invoices),
            "currency": "INR",
        }

    def get_expense_breakdown(self, company_id: str, date_from: str = None, date_to: str = None) -> dict:
        df_default, dt_default = _default_period()
        df = _parse_date(date_from, df_default)
        dt = _parse_date(date_to, dt_default)

        results = self.db.query(
            Expense.category,
            func.sum(Expense.total_amount).label("total"),
            func.count(Expense.id).label("count"),
        ).filter(
            Expense.company_id == uuid.UUID(company_id),
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
            Expense.expense_date >= df,
            Expense.expense_date <= dt,
        ).group_by(Expense.category).order_by(func.sum(Expense.total_amount).desc()).all()

        total = sum(float(r.total) for r in results)
        return {
            "expense_breakdown": [
                {
                    "category": r.category or "Uncategorized",
                    "amount": float(r.total),
                    "count": r.count,
                    "percentage": round(float(r.total) / total * 100, 1) if total > 0 else 0,
                }
                for r in results
            ],
            "total_expenses": total,
            "period": f"{df.strftime('%d %b %Y')} to {dt.strftime('%d %b %Y')}",
            "currency": "INR",
        }

    def get_vendor_payables(self, company_id: str) -> dict:
        results = self.db.query(
            Vendor.name,
            func.sum(Expense.total_amount).label("total_purchases"),
        ).join(Expense, Expense.vendor_id == Vendor.id).filter(
            Expense.company_id == uuid.UUID(company_id),
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
        ).group_by(Vendor.id, Vendor.name).order_by(func.sum(Expense.total_amount).desc()).limit(10).all()

        return {
            "vendor_payables": [
                {"vendor": r.name, "total_purchases": float(r.total_purchases)}
                for r in results
            ],
            "currency": "INR",
        }

    def get_inventory_summary(self, company_id: str) -> dict:
        products = self.db.query(Product).filter(
            Product.company_id == uuid.UUID(company_id),
            Product.is_active == True,
            Product.track_inventory == True,
        ).all()

        total_value = sum(float(p.stock_quantity) * float(p.purchase_price) for p in products)
        low_stock = [p for p in products if float(p.stock_quantity) <= float(p.reorder_threshold)]

        return {
            "total_products": len(products),
            "total_inventory_value": total_value,
            "low_stock_count": len(low_stock),
            "low_stock_products": [
                {"name": p.name, "sku": p.sku, "stock": float(p.stock_quantity), "threshold": float(p.reorder_threshold)}
                for p in low_stock[:5]
            ],
            "currency": "INR",
        }

    def get_financial_summary(self, company_id: str) -> dict:
        revenue = self.get_total_revenue(company_id)
        expenses = self.get_total_expenses(company_id)
        outstanding = self.get_customer_outstanding(company_id)
        overdue = self.get_overdue_invoices(company_id)

        return {
            "period": revenue["period"],
            "revenue": revenue["total_revenue"],
            "expenses": expenses["total_expenses"],
            "net_profit": revenue["total_revenue"] - expenses["total_expenses"],
            "profit_margin": round(
                (revenue["total_revenue"] - expenses["total_expenses"]) / revenue["total_revenue"] * 100, 1
            ) if revenue["total_revenue"] > 0 else 0,
            "outstanding_receivables": outstanding["total_outstanding"],
            "overdue_invoices": overdue["count"],
            "overdue_amount": overdue["total_overdue"],
            "currency": "INR",
        }

    def compare_periods(self, company_id: str) -> dict:
        now = datetime.now(timezone.utc)
        curr_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        curr_to = now
        prev_from = curr_from - relativedelta(months=1)
        prev_to = curr_from - timedelta(seconds=1)

        curr_rev = self.get_total_revenue(company_id, curr_from.isoformat(), curr_to.isoformat())
        prev_rev = self.get_total_revenue(company_id, prev_from.isoformat(), prev_to.isoformat())
        curr_exp = self.get_total_expenses(company_id, curr_from.isoformat(), curr_to.isoformat())
        prev_exp = self.get_total_expenses(company_id, prev_from.isoformat(), prev_to.isoformat())

        def pct_change(curr, prev):
            if prev == 0:
                return None
            return round((curr - prev) / prev * 100, 1)

        return {
            "current_period": curr_rev["period"],
            "previous_period": prev_rev["period"],
            "revenue": {
                "current": curr_rev["total_revenue"],
                "previous": prev_rev["total_revenue"],
                "change_percent": pct_change(curr_rev["total_revenue"], prev_rev["total_revenue"]),
            },
            "expenses": {
                "current": curr_exp["total_expenses"],
                "previous": prev_exp["total_expenses"],
                "change_percent": pct_change(curr_exp["total_expenses"], prev_exp["total_expenses"]),
            },
            "currency": "INR",
        }

    def get_tool_definitions(self) -> list:
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_total_revenue",
                    "description": "Get total sales revenue for a period",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_from": {"type": "string", "description": "Start date ISO format (optional, defaults to current month start)"},
                            "date_to": {"type": "string", "description": "End date ISO format (optional, defaults to now)"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_total_expenses",
                    "description": "Get total expenses for a period",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_from": {"type": "string"},
                            "date_to": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_net_profit",
                    "description": "Get net profit (revenue minus expenses) for a period",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_from": {"type": "string"},
                            "date_to": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_top_customers",
                    "description": "Get top customers by revenue",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "n": {"type": "integer", "description": "Number of customers to return (default 5)"},
                            "date_from": {"type": "string"},
                            "date_to": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_customer_outstanding",
                    "description": "Get customers with outstanding receivable balances",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_overdue_invoices",
                    "description": "Get overdue invoices that are past their due date",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_expense_breakdown",
                    "description": "Get breakdown of expenses by category",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date_from": {"type": "string"},
                            "date_to": {"type": "string"},
                        },
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_vendor_payables",
                    "description": "Get vendor purchase totals",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_inventory_summary",
                    "description": "Get inventory summary including low stock alerts",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_financial_summary",
                    "description": "Get a complete financial summary for the current month",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "compare_periods",
                    "description": "Compare current month vs previous month for revenue and expenses",
                    "parameters": {"type": "object", "properties": {}},
                },
            },
        ]

    def call_tool(self, tool_name: str, args: dict, company_id: str) -> dict:
        args["company_id"] = company_id
        tool_map = {
            "get_total_revenue": self.get_total_revenue,
            "get_total_expenses": self.get_total_expenses,
            "get_net_profit": self.get_net_profit,
            "get_top_customers": self.get_top_customers,
            "get_customer_outstanding": self.get_customer_outstanding,
            "get_overdue_invoices": self.get_overdue_invoices,
            "get_expense_breakdown": self.get_expense_breakdown,
            "get_vendor_payables": self.get_vendor_payables,
            "get_inventory_summary": self.get_inventory_summary,
            "get_financial_summary": self.get_financial_summary,
            "compare_periods": self.compare_periods,
        }
        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}
        fn = tool_map[tool_name]
        import inspect
        sig = inspect.signature(fn)
        filtered_args = {k: v for k, v in args.items() if k in sig.parameters}
        return fn(**filtered_args)
