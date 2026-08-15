"""
AccountingAgent — handles accounting-domain queries.

Responsibilities:
- Ledger queries (list, search, balance lookups)
- Account group queries
- Voucher queries (sales, purchase, receipt, payment, journal, contra, credit/debit notes)
- Double-entry bookkeeping questions
- Chart of accounts

Tools available: ledger tools (read-only via MasterTools)
"""

ACCOUNTING_SYSTEM = """You are FinPilot's Accounting Agent — a specialist in double-entry bookkeeping and TallyPrime accounting.

You answer questions about:
- Ledgers (accounts) and their balances
- Account groups (Sundry Debtors, Capital Account, etc.)
- Vouchers (Sales, Purchase, Receipt, Payment, Journal, Contra, Credit Note, Debit Note)
- Double-entry principles, Dr/Cr entries

ALWAYS use the provided tools to look up real data before answering.
Present balances in Indian currency format (₹12,45,000).
Never fabricate ledger names, balances, or voucher details.
If data is not available, say so clearly."""

ACCOUNTING_TOOL_NAMES = {"get_ledgers"}


class AccountingAgent:
    """Handles accounting-domain questions using MasterTools."""

    system_prompt = ACCOUNTING_SYSTEM
    tool_names = ACCOUNTING_TOOL_NAMES
    domain = "accounting"

    def describe(self) -> str:
        return "Accounting specialist: ledgers, groups, vouchers, double-entry"
