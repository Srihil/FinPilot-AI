"""
AI Entity Extraction Agent.

Extracts structured entity data (customer, vendor, product, invoice, expense)
from natural language input using Groq or OpenRouter.
"""
import json
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a financial data extraction assistant for TallyPrime and FinPilot.
Extract structured entity data from natural language. Return ONLY valid JSON:

{
  "entity_type": "<type>",
  "data": { ...fields... },
  "confidence": 0.0-1.0,
  "missing_fields": ["field names that are required but not mentioned"]
}

Supported entity types and their fields:

ACCOUNTING MASTERS:
- ledger: name (required), group (required, e.g. "Sundry Debtors"/"Sundry Creditors"/"Bank Accounts"/"Cash-in-Hand"), opening_balance
- group: name (required), parent (required, e.g. "Current Assets"/"Current Liabilities"/"Capital Account")

INVENTORY MASTERS:
- stock_item: name (required), unit (e.g. "Nos"/"Kg"/"Ltr"), selling_price, cost_price, stock_group
- stock_group: name (required), parent (default "Primary")
- unit: name (required, e.g. "Nos"/"Kg"/"Ltr"/"Pcs"), symbol, decimal_places
- godown: name (required), parent (default "Main Location")

CUSTOMERS & VENDORS (special ledgers):
- customer: name (required), email, phone, address, city, state, gstin, notes
- vendor: name (required), email, phone, address, city, state, gstin, notes

VOUCHERS (TRANSACTIONS):
- sales_invoice: customer_name (required), amount (required), date (YYYY-MM-DD), narration, sales_ledger (default "Sales")
- purchase_bill: vendor_name (required), amount (required), date (YYYY-MM-DD), narration, purchase_ledger (default "Purchases")
- receipt: party_ledger (required, customer name), account_ledger (bank/cash, default "Cash"), amount (required), date (YYYY-MM-DD), narration
- payment: party_ledger (required, vendor name), account_ledger (bank/cash, default "Cash"), amount (required), date (YYYY-MM-DD), narration
- journal: dr_ledger (required), cr_ledger (required), amount (required), date (YYYY-MM-DD), narration
- credit_note: party_ledger (required, customer), amount (required), date (YYYY-MM-DD), narration, sales_ledger (default "Sales")
- debit_note: party_ledger (required, vendor), amount (required), date (YYYY-MM-DD), narration, purchase_ledger (default "Purchases")
- contra: from_account (required), to_account (required), amount (required), date (YYYY-MM-DD), narration
- expense: title (required), amount (required), category, date (YYYY-MM-DD), vendor_name, description
- custom_voucher: voucher_type_name (required, the EXACT custom type name as stated by user), party_ledger, amount (required), date (YYYY-MM-DD), narration, sales_ledger (if sales-type), purchase_ledger (if purchase-type), account_ledger (if receipt/payment-type), dr_ledger, cr_ledger (if journal-type)

IMPORTANT rules for entity_type:
- Cash/bank transfer → always use "contra" (never "voucher" or "transfer")
- Money received from customer → always "receipt"
- Money paid to vendor → always "payment"
- General ledger Dr/Cr entry → always "journal"
- If user mentions a specific named voucher type that is NOT one of the standard types above (e.g. "GST Bill", "Tax Invoice", "Salary Payment") → use "custom_voucher" and set voucher_type_name to the exact name mentioned
- Never return entity_type as "voucher" — always use the specific type above

Date format: always YYYY-MM-DD. If no year mentioned, assume current year 2026.
For amounts, extract the numeric value only (no currency symbols).
Return ONLY JSON — no markdown, no explanation."""


class DemoEntityAgent:
    """Simple rule-based fallback when no AI provider is configured."""

    def extract(self, text: str) -> dict:
        text_lower = text.lower()

        if any(w in text_lower for w in ["receipt", "received from", "money received"]):
            entity_type = "receipt"
        elif any(w in text_lower for w in ["payment", "paid to", "money paid"]):
            entity_type = "payment"
        elif any(w in text_lower for w in ["journal", "jv ", "dr ", "cr "]):
            entity_type = "journal"
        elif any(w in text_lower for w in ["credit note", "sales return"]):
            entity_type = "credit_note"
        elif any(w in text_lower for w in ["debit note", "purchase return"]):
            entity_type = "debit_note"
        elif any(w in text_lower for w in ["contra", "transfer", "bank transfer"]):
            entity_type = "contra"
        elif any(w in text_lower for w in ["customer", "client", "buyer", "debtor"]):
            entity_type = "customer"
        elif any(w in text_lower for w in ["vendor", "supplier", "creditor"]):
            entity_type = "vendor"
        elif any(w in text_lower for w in ["stock group", "item group"]):
            entity_type = "stock_group"
        elif any(w in text_lower for w in ["stock item", "product", "inventory", "item"]):
            entity_type = "stock_item"
        elif any(w in text_lower for w in ["unit of measure", "uom", " unit"]):
            entity_type = "unit"
        elif any(w in text_lower for w in ["godown", "warehouse", "location"]):
            entity_type = "godown"
        elif any(w in text_lower for w in ["group", "account group"]):
            entity_type = "group"
        elif any(w in text_lower for w in ["ledger", "account"]):
            entity_type = "ledger"
        elif any(w in text_lower for w in ["sales invoice", "sale", "invoice"]):
            entity_type = "sales_invoice"
        elif any(w in text_lower for w in ["purchase bill", "purchase", "bill"]):
            entity_type = "purchase_bill"
        elif any(w in text_lower for w in ["expense", "cost", "paid", "spent"]):
            entity_type = "expense"
        else:
            entity_type = "expense"

        return {
            "entity_type": entity_type,
            "data": {"name": text[:50], "title": text[:50]},
            "confidence": 0.4,
            "missing_fields": ["Please verify all extracted fields"],
        }


class LLMEntityAgent:
    def extract(self, text: str) -> dict:
        if settings.AI_PROVIDER == "groq":
            api_url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            }
            model = settings.GROQ_MODEL
        else:
            api_url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            }
            model = settings.AI_MODEL

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "max_tokens": 512,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        with httpx.Client(timeout=30) as client:
            resp = client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)


class EntityAgent:
    def extract(self, text: str) -> dict:
        # Try LLM if API keys are configured
        api_key = settings.GROQ_API_KEY if settings.AI_PROVIDER == "groq" else settings.OPENROUTER_API_KEY
        if not api_key or settings.is_demo_mode:
            return DemoEntityAgent().extract(text)

        try:
            result = LLMEntityAgent().extract(text)
            # Validate expected keys are present
            if "entity_type" not in result or "data" not in result:
                raise ValueError("Unexpected response shape from LLM")
            return result
        except Exception as e:
            logger.warning("LLMEntityAgent failed, falling back to demo: %s", e)
            return DemoEntityAgent().extract(text)
