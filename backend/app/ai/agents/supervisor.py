"""
SupervisorAgent — routes user requests to the correct specialized domain agent.

Responsibilities:
- Understand intent: accounting | inventory | tally | reporting | orders | parties | create | general
- Route to the appropriate agent
- Never execute business logic itself
"""
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

SUPERVISOR_SYSTEM = """You are the FinPilot AI supervisor. Your ONLY job is to classify the user's question into exactly one intent word.

Intents:
- accounting    → ledgers, account groups, vouchers, journal entries, double-entry, Dr/Cr, P&L
- inventory     → stock items, products, stock groups, units of measure, godowns, warehouses, physical stock
- tally         → TallyPrime connection, sync jobs, failed syncs, connector status, heartbeat, pairing
- reporting     → revenue, sales, expenses, profit, margin, financial summary, trends, MoM comparison
- orders        → sales orders, purchase orders, order status, order fulfilment
- parties       → customers, vendors, debtors, creditors, outstanding, receivables, payables
- create        → create, add, make, new entity (ledger/customer/vendor/stock item/voucher etc.)
- general       → anything else

Reply with ONLY the intent word. No punctuation, no explanation."""

INTENT_KEYWORDS = {
    "tally": ["tally", "sync", "connector", "heartbeat", "connection", "failed sync", "pairing", "reconnect"],
    "inventory": ["stock", "inventory", "godown", "warehouse", "unit of measure", "uom", "reorder", "physical stock"],
    "accounting": ["ledger", "account group", "voucher", "journal", "contra", "receipt", "payment", "credit note", "debit note"],
    "reporting": ["revenue", "expense", "profit", "margin", "financial", "summary", "performance", "turnover", "report"],
    "orders": ["order", "sales order", "purchase order", "fulfilment", "fulfillment"],
    "parties": ["customer", "vendor", "supplier", "debtor", "creditor", "outstanding", "receivable", "payable"],
    "create": ["create", "add new", "make a", "new ledger", "new customer", "new vendor", "new stock", "new unit", "new godown"],
}

VALID_INTENTS = {"accounting", "inventory", "tally", "reporting", "orders", "parties", "create", "general"}


def _keyword_detect(query: str) -> str:
    q = query.lower()
    for intent, keywords in INTENT_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return intent
    return "general"


class SupervisorAgent:
    """Routes user intent to the correct domain agent."""

    def classify(self, query: str, provider: str) -> str:
        """Return one of the VALID_INTENTS for the given query."""
        api_key = settings.GROQ_API_KEY if provider == "groq" else settings.OPENROUTER_API_KEY
        if not api_key or settings.is_demo_mode:
            return _keyword_detect(query)

        try:
            from app.agents.finance_agent import GroqAgent, OpenRouterAgent
            llm = GroqAgent() if provider == "groq" else OpenRouterAgent()
            resp = llm.chat(
                messages=[
                    {"role": "system", "content": SUPERVISOR_SYSTEM},
                    {"role": "user", "content": query},
                ],
                tools=[],
            )
            raw = (resp["choices"][0]["message"].get("content") or "").strip().lower()
            return raw if raw in VALID_INTENTS else _keyword_detect(query)
        except Exception as e:
            logger.warning("Supervisor LLM failed, using keywords: %s", e)
            return _keyword_detect(query)
