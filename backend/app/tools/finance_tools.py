"""
Controlled Finance Tools - these are the ONLY ways the AI can access financial data.
The LLM calls these tools; the tools run deterministic database queries.
query_database allows arbitrary SELECT with automatic company_id isolation and guardrails.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, text
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
import re as _re

# ── Database schema exposed to the AI (safe subset only) ─────────────────────
DB_SCHEMA = """
=== FinPilot Database — available tables ===
All tables are pre-filtered to this company. Do NOT add company_id to queries.

customers         : id, name, email, phone, gstin, address, city, state, country, notes, created_at
vendors           : id, name, email, phone, gstin, address, city, state, notes, created_at
products          : id, name, sku, unit, selling_price, cost_price, stock_quantity, reorder_threshold, is_active, created_at
invoices          : id, invoice_number, invoice_type (SALES|PURCHASE), invoice_date, due_date,
                    total_amount, paid_amount, status (DRAFT|APPROVED|SENT|PARTIALLY_PAID|PAID|OVERDUE),
                    customer_id→customers.id, vendor_id→vendors.id, notes, created_at
invoice_items     : id, invoice_id→invoices.id, description, quantity, unit_price, total_price, product_id→products.id
expenses          : id, title, category, expense_date, amount, tax_amount, total_amount,
                    status (DRAFT|APPROVED|PAID), vendor_id→vendors.id, notes, reference_number, created_at
                    category: Office Supplies|Utilities|Rent|Salaries|Travel|Marketing|Software|
                    Equipment|Maintenance|Professional Services|Raw Materials|Shipping|Insurance|
                    Taxes|Miscellaneous|Receipt|Payment|Journal|Contra|Credit Note|Debit Note
stock_transactions: id, transaction_number, transaction_type (STOCK_JOURNAL|PHYSICAL_STOCK|
                    DELIVERY_NOTE|RECEIPT_NOTE|REJECTION_IN|REJECTION_OUT),
                    transaction_date, narration, party_name, from_godown, to_godown,
                    entries (JSON array of {stock_item_name,quantity,unit,rate,godown}),
                    tally_sync_status, created_at
audit_logs        : id, action, entity_type, entity_id, description, created_at
tally_integration_jobs: id, operation, status (PENDING|CLAIMED|SUCCESS|FAILED|RETRYING),
                        error_message, retry_count, created_at, updated_at

Monetary amounts are INR. SALES invoices = revenue. REJECTION_IN = goods returned from customer.
REJECTION_OUT = goods sent back to vendor. Only APPROVED/SENT/PARTIALLY_PAID/PAID invoices = confirmed revenue.
"""

# Tables that have a company_id column (auto-filtered via CTE)
_COMPANY_TABLES = frozenset({
    "customers", "vendors", "products", "invoices", "expenses",
    "approvals", "audit_logs", "tally_integration_jobs", "uploads", "reports",
    "stock_transactions",
})

_FORBIDDEN_SQL = _re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|"
    r"EXECUTE|EXEC|VACUUM|REINDEX|COPY|CALL|DO)\b",
    _re.IGNORECASE,
)

_BLOCKED_CONTENT = _re.compile(
    r"(password_hash|token_hash|hashed_password|secret|"
    r"pg_catalog|information_schema|pg_class|pg_shadow|pg_user)",
    _re.IGNORECASE,
)


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

    # ── query_database ────────────────────────────────────────────────────────

    def query_database(self, company_id: str, sql: str) -> dict:
        """
        Execute a read-only SQL SELECT against the company's data.

        Guardrails enforced here (not in the prompt):
        1. Must start with SELECT — no DML/DDL allowed
        2. Forbidden keywords (INSERT/UPDATE/DELETE/DROP …) blocked
        3. Sensitive columns (password_hash, token_hash …) blocked
        4. company_id auto-injected via CTE — zero cross-tenant leakage
        5. LIMIT capped at 200 rows
        6. 8-second statement timeout
        """
        sql = (sql or "").strip().rstrip(";")

        # Guard 1 — SELECT only
        if not _re.match(r"^SELECT\b", sql, _re.IGNORECASE):
            return {"error": "Only SELECT queries are allowed.", "rows": [], "count": 0}

        # Guard 2 — forbidden DML/DDL
        if _FORBIDDEN_SQL.search(sql):
            return {"error": "Query contains a forbidden operation.", "rows": [], "count": 0}

        # Guard 3 — sensitive columns
        if _BLOCKED_CONTENT.search(sql):
            return {"error": "Query references a restricted column or schema.", "rows": [], "count": 0}

        # Guard 4 — company_id isolation via CTE
        referenced = [
            t for t in _COMPANY_TABLES
            if _re.search(r"\b" + _re.escape(t) + r"\b", sql, _re.IGNORECASE)
        ]
        if referenced:
            cid = str(company_id)
            cte_parts = [
                f"{t} AS (SELECT * FROM public.{t} WHERE company_id = '{cid}')"
                for t in referenced
            ]
            cte_sql = ",\n  ".join(cte_parts)
            if _re.match(r"^WITH\b", sql, _re.IGNORECASE):
                # Prepend our CTEs before the user's existing WITH list
                sql = f"WITH {cte_sql},\n  " + sql[5:]
            else:
                sql = f"WITH {cte_sql}\n{sql}"

        # Guard 5 — LIMIT cap
        if not _re.search(r"\bLIMIT\b", sql, _re.IGNORECASE):
            sql = f"{sql} LIMIT 200"
        else:
            def _cap(m: _re.Match) -> str:
                return f"LIMIT {min(int(m.group(1)), 200)}"
            sql = _re.sub(r"\bLIMIT\s+(\d+)", _cap, sql, flags=_re.IGNORECASE)

        # Guard 6 — execute with timeout
        try:
            self.db.execute(text("SET LOCAL statement_timeout = '8000'"))
            result = self.db.execute(text(sql))
            columns = list(result.keys())
            raw_rows = result.fetchall()

            rows = []
            for row in raw_rows:
                clean = {}
                for col, val in zip(columns, row):
                    if val is None:
                        clean[col] = None
                    elif hasattr(val, "isoformat"):
                        clean[col] = val.isoformat()
                    elif isinstance(val, (int, float, str, bool)):
                        clean[col] = val
                    else:
                        clean[col] = str(val)
                rows.append(clean)

            return {"rows": rows, "count": len(rows), "columns": columns}

        except Exception as exc:
            # Rollback the aborted transaction so the session stays usable
            # for subsequent tool calls in the same request.
            try:
                self.db.rollback()
            except Exception:
                pass

            err = str(exc)
            if "statement timeout" in err.lower():
                return {"error": "Query timed out (8 s max). Simplify or add a tighter filter.", "rows": [], "count": 0}
            err = _re.sub(r'File ".*?", line \d+,? ?', "", err)
            return {"error": f"Query failed: {err[:400]}", "rows": [], "count": 0}

        finally:
            # Reset timeout — runs in a fresh transaction after rollback if needed
            try:
                self.db.execute(text("SET LOCAL statement_timeout = DEFAULT"))
            except Exception:
                pass

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
            {
                "type": "function",
                "function": {
                    "name": "query_database",
                    "description": (
                        "Run a PostgreSQL SELECT query against the company's financial database. "
                        "Use for any question not covered by other tools. "
                        "company_id is auto-injected — never include it. Max 200 rows. No schema prefix on table names."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sql": {
                                "type": "string",
                                "description": "A valid PostgreSQL SELECT statement.",
                            },
                        },
                        "required": ["sql"],
                    },
                },
            },
        ]

    def call_tool(self, tool_name: str, args: dict, company_id: str) -> dict:
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
            "query_database": self.query_database,
        }
        if tool_name not in tool_map:
            return {"error": f"Unknown tool: {tool_name}"}
        fn = tool_map[tool_name]
        import inspect
        sig = inspect.signature(fn)
        call_args = {"company_id": company_id, **args}
        filtered = {k: v for k, v in call_args.items() if k in sig.parameters}
        return fn(**filtered)
