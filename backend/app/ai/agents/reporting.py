"""
ReportingAgent — handles financial reporting and analytics queries.

Responsibilities:
- Revenue / sales totals and trends
- Expense breakdowns by category
- Profit & loss analysis
- Month-over-month comparisons
- Outstanding receivables / payables
- Overdue invoices

Tools available: FinanceTools (all read-only financial analytics tools)
"""

REPORTING_SYSTEM = """You are FinPilot's Reporting Agent — a specialist in financial analysis and business intelligence.

You answer questions about:
- Revenue, sales, and income figures
- Expense totals and category breakdowns
- Net profit, profit margins
- Month-on-month and period comparisons
- Customer revenue rankings
- Outstanding receivables (money owed to us)
- Vendor payables (money we owe)
- Overdue invoices

ALWAYS call the appropriate tool to fetch real data before answering.
Format numbers in Indian currency (₹12,45,000). Show percentage changes with ↑↓ arrows.
Be specific about the time period covered. Never fabricate financial figures.
If the requested data isn't available, say so and suggest an alternative query."""

REPORTING_TOOL_NAMES = {
    "get_total_revenue", "get_total_expenses", "get_net_profit",
    "get_top_customers", "get_customer_outstanding", "get_overdue_invoices",
    "get_expense_breakdown", "get_vendor_payables", "get_inventory_summary",
    "get_financial_summary", "compare_periods",
}


class ReportingAgent:
    """Handles financial reporting using FinanceTools."""

    system_prompt = REPORTING_SYSTEM
    tool_names = REPORTING_TOOL_NAMES
    domain = "reporting"

    def describe(self) -> str:
        return "Reporting specialist: revenue, expenses, profit, receivables, payables, trends"
