"""
PartyAgent — handles customer and vendor queries.

Responsibilities:
- Customer list and search
- Vendor list and search
- Outstanding receivables per customer
- Vendor payables
- Party-level financial summaries

Tools available: MasterTools (get_customers, get_vendors) + FinanceTools (receivables, payables)
"""

PARTIES_SYSTEM = """You are FinPilot's Party Management Agent — a specialist in customers and vendors.

You answer questions about:
- Customer list (Sundry Debtors), contacts, GSTIN
- Vendor list (Sundry Creditors), contacts, GSTIN
- Which customers owe money (outstanding receivables)
- How much we owe vendors (payables)
- Top customers by revenue
- Overdue customer invoices

ALWAYS use tools to fetch real party and financial data.
Format outstanding amounts in Indian currency (₹12,45,000).
When a customer owes money, say so clearly with the exact amount.
Never fabricate party names, contact details, or financial figures."""

PARTIES_TOOL_NAMES = {
    "get_customers", "get_vendors",
    "get_customer_outstanding", "get_vendor_payables", "get_overdue_invoices", "get_top_customers",
}


class PartyAgent:
    """Handles customer and vendor queries using MasterTools + FinanceTools."""

    system_prompt = PARTIES_SYSTEM
    tool_names = PARTIES_TOOL_NAMES
    domain = "parties"

    def describe(self) -> str:
        return "Party specialist: customers, vendors, outstanding receivables, payables"
