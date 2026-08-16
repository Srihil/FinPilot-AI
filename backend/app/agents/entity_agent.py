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

══════════════════════════════════════════════════════════════
STEP 1 — CUSTOM VOUCHER CHECK (do this before anything else)
══════════════════════════════════════════════════════════════

The 8 STANDARD transaction types (these exact strings only):
  "Sales Invoice" | "Purchase Bill" | "Receipt" | "Payment" |
  "Journal"       | "Credit Note"   | "Debit Note" | "Contra"

RULE: If the user names a transaction type that is NOT exactly one of
those 8 strings above → entity_type MUST be "custom_voucher".

This rule is ABSOLUTE. It overrides everything else. It does not matter
if the custom name contains common words like "cash", "payment",
"invoice", "receipt", "bill", "salary", "GST", "tax", "petty" etc.

HOW TO DETECT the custom type name:
  Look for the pattern: "Create/Make/Record/Enter a <TYPE> ..."
  The <TYPE> is the voucher type name. Extract it exactly as written.
  Stop at words like "for", "of", "entry", "dated", "on", "from".

STRICT EXAMPLES — memorise these:
  "Create a Petty Cash payment..."   → custom_voucher, name="Petty Cash"
  "Create a Petty Cash entry..."     → custom_voucher, name="Petty Cash"
  "Create a Petty Cash..."           → custom_voucher, name="Petty Cash"
  "Create a GST Bill for..."         → custom_voucher, name="GST Bill"
  "Create a Tax Invoice for..."      → custom_voucher, name="Tax Invoice"
  "Create a Cash Memo for..."        → custom_voucher, name="Cash Memo"
  "Create a Salary payment..."       → custom_voucher, name="Salary"
  "Create a Salary entry..."         → custom_voucher, name="Salary"
  "Create an Export Invoice..."      → custom_voucher, name="Export Invoice"
  "Record a Bank Transfer..."        → custom_voucher, name="Bank Transfer"
  "Create an Advance Receipt..."     → custom_voucher, name="Advance Receipt"
  "Make a Proforma Invoice..."       → custom_voucher, name="Proforma Invoice"
  "Create a Purchase payment..."     → payment (standard — no custom name)
  "Create a sales receipt..."        → receipt (standard — no custom name)
  "Record a payment to vendor..."    → payment (standard — no custom name)

══════════════════════════════════════════════════════════════
STEP 2 — STANDARD TYPES (only if Step 1 found no custom name)
══════════════════════════════════════════════════════════════

ACCOUNTING MASTERS:
- ledger: name (required), group (required, e.g. "Sundry Debtors"/"Sundry Creditors"/"Bank Accounts"/"Cash-in-Hand"), opening_balance
- group: name (required), parent (required, e.g. "Current Assets"/"Current Liabilities"/"Capital Account")

INVENTORY MASTERS:
- stock_item: name (required), unit (e.g. "Nos"/"Kg"/"Ltr"), selling_price, cost_price, stock_group
- stock_group: name (required), parent (default "Primary")
- unit: name (required, e.g. "Nos"/"Kg"/"Ltr"/"Pcs"), symbol, decimal_places
- godown: name (required), parent (default "Main Location")

CUSTOMERS & VENDORS:
- customer: name (required), email, phone, address, city, state, gstin, notes
- vendor: name (required), email, phone, address, city, state, gstin, notes

STANDARD VOUCHERS:
- sales_invoice: customer_name (required), amount (required), date (YYYY-MM-DD), narration, sales_ledger (default "Sales")
- purchase_bill: vendor_name (required), amount (required), date (YYYY-MM-DD), narration, purchase_ledger (default "Purchases")
- receipt: party_ledger (required), account_ledger (default "Cash"), amount (required), date (YYYY-MM-DD), narration
- payment: party_ledger (required), account_ledger (default "Cash"), amount (required), date (YYYY-MM-DD), narration
- journal: dr_ledger (required), cr_ledger (required), amount (required), date (YYYY-MM-DD), narration
- credit_note: party_ledger (required), amount (required), date (YYYY-MM-DD), narration, sales_ledger (default "Sales")
- debit_note: party_ledger (required), amount (required), date (YYYY-MM-DD), narration, purchase_ledger (default "Purchases")
- contra: from_account (required), to_account (required), amount (required), date (YYYY-MM-DD), narration
- expense: title (required), amount (required), category, date (YYYY-MM-DD), vendor_name, description

CUSTOM VOUCHER fields:
- custom_voucher: voucher_type_name (required, EXACT name as user stated),
    party_ledger, amount (required), date (YYYY-MM-DD), narration,
    account_ledger (for payment/receipt-based types),
    sales_ledger (for sales-based types, default "Sales"),
    purchase_ledger (for purchase-based types, default "Purchases"),
    dr_ledger, cr_ledger (for journal-based types)

Standard routing (ONLY when no custom name found):
- Cash/bank transfer between own accounts → "contra"
- Money received from customer → "receipt"
- Money paid to vendor/supplier → "payment"
- Dr/Cr ledger adjustment → "journal"
- Sales return → "credit_note"
- Purchase return → "debit_note"

Date: always YYYY-MM-DD. If no year, assume 2026.
Amounts: numeric only, strip ₹ and commas.
Return ONLY JSON — no markdown, no explanation."""


class DemoEntityAgent:
    """Simple rule-based fallback when no AI provider is configured."""

    # Exact standard type phrases — anything else naming a type is custom
    _STANDARD_PHRASES = {
        "sales invoice", "purchase bill", "receipt", "payment",
        "journal", "credit note", "debit note", "contra",
        "expense", "sales return", "purchase return",
    }

    @classmethod
    def _extract_custom_type(cls, text: str) -> str | None:
        """Return the custom voucher type name if the text names a non-standard type."""
        import re
        # Pattern: "Create/Make/Record/Enter a <TYPE> [for/entry/...]"
        m = re.search(
            r'(?:create|make|record|enter|add)\s+a(?:n)?\s+([A-Z][A-Za-z\s]{1,30}?)(?:\s+(?:for|of|entry|dated|on|from|to)\b|$)',
            text, re.IGNORECASE
        )
        if m:
            candidate = m.group(1).strip()
            if candidate.lower() not in cls._STANDARD_PHRASES:
                return candidate
        return None

    def extract(self, text: str) -> dict:
        import re
        text_lower = text.lower()

        # ── Step 1: Custom voucher type check ────────────────────────────
        custom_type = self._extract_custom_type(text)
        if custom_type:
            # Extract amount
            amount_m = re.search(r'[₹]?\s*([\d,]+)', text)
            amount = amount_m.group(1).replace(',', '') if amount_m else "0"
            # Extract party (after "for")
            party_m = re.search(r'for\s+([A-Za-z\s&]+?)(?:\s+for|\s+₹|\s+\d|$)', text, re.IGNORECASE)
            party = party_m.group(1).strip() if party_m else ""
            return {
                "entity_type": "custom_voucher",
                "data": {
                    "voucher_type_name": custom_type,
                    "party_ledger": party,
                    "amount": amount,
                    "account_ledger": "Cash",
                    "narration": text[:80],
                },
                "confidence": 0.5,
                "missing_fields": ["date", "Please verify all extracted fields"],
            }

        # ── Step 2: Standard types ────────────────────────────────────────
        if any(w in text_lower for w in ["received from", "money received"]):
            entity_type = "receipt"
        elif "receipt" in text_lower and "advance" not in text_lower:
            entity_type = "receipt"
        elif any(w in text_lower for w in ["paid to", "money paid"]):
            entity_type = "payment"
        elif "payment" in text_lower and "petty" not in text_lower and "salary" not in text_lower:
            entity_type = "payment"
        elif any(w in text_lower for w in ["journal", "jv ", "dr ", "cr "]):
            entity_type = "journal"
        elif any(w in text_lower for w in ["credit note", "sales return"]):
            entity_type = "credit_note"
        elif any(w in text_lower for w in ["debit note", "purchase return"]):
            entity_type = "debit_note"
        elif any(w in text_lower for w in ["contra", "bank transfer", "cash transfer"]):
            entity_type = "contra"
        elif any(w in text_lower for w in ["customer", "client", "buyer", "debtor"]):
            entity_type = "customer"
        elif any(w in text_lower for w in ["vendor", "supplier", "creditor"]):
            entity_type = "vendor"
        elif any(w in text_lower for w in ["stock group", "item group"]):
            entity_type = "stock_group"
        elif any(w in text_lower for w in ["stock item", "product", "inventory"]):
            entity_type = "stock_item"
        elif any(w in text_lower for w in ["unit of measure", "uom", " unit"]):
            entity_type = "unit"
        elif any(w in text_lower for w in ["godown", "warehouse", "location"]):
            entity_type = "godown"
        elif any(w in text_lower for w in ["account group"]):
            entity_type = "group"
        elif any(w in text_lower for w in ["ledger", "account"]):
            entity_type = "ledger"
        elif any(w in text_lower for w in ["sales invoice", "sale", "invoice"]):
            entity_type = "sales_invoice"
        elif any(w in text_lower for w in ["purchase bill", "purchase", "bill"]):
            entity_type = "purchase_bill"
        elif any(w in text_lower for w in ["expense", "cost", "spent"]):
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
