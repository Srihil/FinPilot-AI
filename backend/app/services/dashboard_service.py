from sqlalchemy.orm import Session
from sqlalchemy import func, and_, extract
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.expense import Expense, ExpenseStatus
from app.models.payment import Payment
from app.models.approval import Approval, ApprovalStatus
from app.models.customer import Customer
from app.models.product import Product
from datetime import datetime, timezone, timedelta
from dateutil.relativedelta import relativedelta
import uuid


class DashboardService:
    def get_overview(self, db: Session, company_id: uuid.UUID,
                     date_from: datetime = None, date_to: datetime = None) -> dict:
        now = datetime.now(timezone.utc)
        if not date_from:
            date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if not date_to:
            date_to = now

        prev_from = date_from - relativedelta(months=1)
        prev_to = date_to - relativedelta(months=1)

        def get_revenue(df, dt):
            return db.query(func.sum(Invoice.total_amount)).filter(
                Invoice.company_id == company_id,
                Invoice.invoice_type == InvoiceType.SALES,
                Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                                    InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID]),
                Invoice.invoice_date >= df,
                Invoice.invoice_date <= dt,
            ).scalar() or 0

        def get_expenses(df, dt):
            return db.query(func.sum(Expense.total_amount)).filter(
                Expense.company_id == company_id,
                Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
                Expense.expense_date >= df,
                Expense.expense_date <= dt,
            ).scalar() or 0

        revenue = float(get_revenue(date_from, date_to))
        expenses = float(get_expenses(date_from, date_to))
        prev_revenue = float(get_revenue(prev_from, prev_to))
        prev_expenses = float(get_expenses(prev_from, prev_to))

        revenue_growth = ((revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0
        expense_growth = ((expenses - prev_expenses) / prev_expenses * 100) if prev_expenses > 0 else 0

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

        pending_approvals = db.query(func.count(Approval.id)).filter(
            Approval.company_id == company_id,
            Approval.status == ApprovalStatus.PENDING,
        ).scalar() or 0

        recent_transactions = db.query(Invoice).filter(
            Invoice.company_id == company_id
        ).order_by(Invoice.created_at.desc()).limit(10).all()

        return {
            "total_revenue": revenue,
            "total_expenses": expenses,
            "net_profit": revenue - expenses,
            "outstanding_receivables": outstanding_receivables,
            "outstanding_payables": outstanding_payables,
            "revenue_growth": round(revenue_growth, 1),
            "expense_growth": round(expense_growth, 1),
            "pending_approvals_count": pending_approvals,
            "recent_transactions": [
                {
                    "id": str(t.id),
                    "invoice_number": t.invoice_number,
                    "type": t.invoice_type.value,
                    "status": t.status.value,
                    "total_amount": float(t.total_amount),
                    "invoice_date": t.invoice_date.isoformat(),
                }
                for t in recent_transactions
            ],
        }

    def get_charts(self, db: Session, company_id: uuid.UUID) -> dict:
        # Monthly revenue/expenses for last 12 months
        monthly_data = []
        now = datetime.now(timezone.utc)

        for i in range(11, -1, -1):
            month_start = (now - relativedelta(months=i)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_end = month_start + relativedelta(months=1) - timedelta(seconds=1)

            rev = float(db.query(func.sum(Invoice.total_amount)).filter(
                Invoice.company_id == company_id,
                Invoice.invoice_type == InvoiceType.SALES,
                Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.SENT,
                                     InvoiceStatus.PARTIALLY_PAID, InvoiceStatus.PAID]),
                Invoice.invoice_date >= month_start,
                Invoice.invoice_date <= month_end,
            ).scalar() or 0)

            exp = float(db.query(func.sum(Expense.total_amount)).filter(
                Expense.company_id == company_id,
                Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
                Expense.expense_date >= month_start,
                Expense.expense_date <= month_end,
            ).scalar() or 0)

            monthly_data.append({
                "month": month_start.strftime("%b %Y"),
                "revenue": rev,
                "expenses": exp,
                "profit": rev - exp,
            })

        # Expense categories
        expense_categories = db.query(
            Expense.category,
            func.sum(Expense.total_amount).label("total")
        ).filter(
            Expense.company_id == company_id,
            Expense.status.in_([ExpenseStatus.APPROVED, ExpenseStatus.PAID]),
            Expense.category.isnot(None),
        ).group_by(Expense.category).order_by(func.sum(Expense.total_amount).desc()).limit(8).all()

        # Top customers
        from app.models.customer import Customer
        top_customers = db.query(
            Customer.name,
            func.sum(Invoice.total_amount).label("revenue")
        ).join(Invoice, Invoice.customer_id == Customer.id).filter(
            Invoice.company_id == company_id,
            Invoice.invoice_type == InvoiceType.SALES,
            Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.PAID, InvoiceStatus.SENT]),
        ).group_by(Customer.id, Customer.name).order_by(func.sum(Invoice.total_amount).desc()).limit(5).all()

        return {
            "monthly_data": monthly_data,
            "expense_categories": [{"name": r.category, "value": float(r.total)} for r in expense_categories],
            "top_customers": [{"name": r.name, "revenue": float(r.revenue)} for r in top_customers],
        }


dashboard_service = DashboardService()
