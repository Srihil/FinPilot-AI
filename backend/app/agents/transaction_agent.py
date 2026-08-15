"""
AI Transaction Proposal Agent.

Flow:
  User describes a transaction in natural language
  → AI extracts structured data
  → Validation
  → Draft preview returned to user
  → Human approves/rejects
  → Backend commits if approved

The AI NEVER directly writes to the database.
"""
import json
import re
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.customer import Customer
from app.models.vendor import Vendor
from typing import Optional
import uuid


EXTRACTION_PROMPT = """You are a financial data extraction assistant.

Extract structured transaction data from the user's natural language description.
Return ONLY a valid JSON object with these fields:

{
  "transaction_type": "expense|sales_invoice|purchase_invoice|payment_received|payment_made",
  "vendor_name": "string or null",
  "customer_name": "string or null",
  "category": "string or null",
  "amount": number,
  "tax_amount": number,
  "description": "string",
  "date": "YYYY-MM-DD or null",
  "reference_number": "string or null",
  "line_items": [] or [{"description": "...", "quantity": 1, "unit_price": 0}],
  "confidence": 0.0 to 1.0,
  "missing_fields": ["list of fields that seem required but weren't mentioned"]
}

Only extract what is explicitly mentioned. Do not invent data."""


class DemoTransactionExtractor:
    """Rule-based extractor for demo mode."""

    def extract(self, text: str) -> dict:
        text_lower = text.lower()

        # Detect transaction type
        if any(w in text_lower for w in ["expense", "paid", "purchase", "bought", "spent"]):
            tx_type = "expense"
        elif any(w in text_lower for w in ["invoice", "sold", "sale", "charged", "billed"]):
            tx_type = "sales_invoice"
        elif any(w in text_lower for w in ["received", "payment from", "collected"]):
            tx_type = "payment_received"
        else:
            tx_type = "expense"

        # Extract amount - look for numbers
        amount = 0
        amount_patterns = [
            r"₹\s*([\d,]+(?:\.\d{2})?)",
            r"rs\.?\s*([\d,]+(?:\.\d{2})?)",
            r"inr\s*([\d,]+(?:\.\d{2})?)",
            r"\b(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\b",
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, text_lower)
            if match:
                amount_str = match.group(1).replace(",", "")
                try:
                    amount = float(amount_str)
                    break
                except ValueError:
                    pass

        # Detect category keywords
        category_map = {
            "office": "Office Supplies",
            "stationery": "Office Supplies",
            "electricity": "Utilities",
            "internet": "Utilities",
            "rent": "Rent",
            "salary": "Salaries",
            "travel": "Travel",
            "marketing": "Marketing",
            "software": "Software",
            "equipment": "Equipment",
            "maintenance": "Maintenance",
            "raw material": "Raw Materials",
            "shipping": "Shipping",
            "insurance": "Insurance",
        }
        category = "Miscellaneous"
        for kw, cat in category_map.items():
            if kw in text_lower:
                category = cat
                break

        # Extract potential vendor/customer name (word after "from"/"to")
        vendor_name = None
        customer_name = None
        from_match = re.search(r"\bfrom\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:for|of|worth|at|in)|\.|$)", text)
        to_match = re.search(r"\bto\s+([A-Z][a-zA-Z\s]+?)(?:\s+(?:for|of|worth|at|in)|\.|$)", text)

        if from_match and tx_type in ("expense", "purchase_invoice"):
            vendor_name = from_match.group(1).strip()
        if to_match and tx_type == "payment_received":
            customer_name = to_match.group(1).strip()

        missing = []
        if not amount:
            missing.append("amount")
        if tx_type == "expense" and not vendor_name:
            missing.append("vendor_name")

        return {
            "transaction_type": tx_type,
            "vendor_name": vendor_name,
            "customer_name": customer_name,
            "category": category,
            "amount": amount,
            "tax_amount": round(amount * 0.18, 2) if amount else 0,
            "description": text,
            "date": None,
            "reference_number": None,
            "line_items": [],
            "confidence": 0.7 if amount else 0.3,
            "missing_fields": missing,
        }


class LLMTransactionExtractor:
    def extract(self, text: str) -> dict:
        if settings.AI_PROVIDER == "groq":
            api_url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {"Authorization": f"Bearer {settings.GROQ_API_KEY}", "Content-Type": "application/json"}
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
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": text},
            ],
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
        }
        with httpx.Client(timeout=30) as client:
            resp = client.post(api_url, json=payload, headers=headers)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            return json.loads(content)


class TransactionAgent:
    def __init__(self, db: Session):
        self.db = db

    def propose(self, text: str, company_id: str) -> dict:
        if settings.is_demo_mode:
            extractor = DemoTransactionExtractor()
        else:
            try:
                extractor = LLMTransactionExtractor()
            except Exception:
                extractor = DemoTransactionExtractor()

        extracted = extractor.extract(text)
        validated = self._validate(extracted, company_id)
        return {
            "proposed": extracted,
            "validation": validated,
            "is_demo": settings.is_demo_mode,
        }

    def _validate(self, data: dict, company_id: str) -> dict:
        errors = []
        warnings = []

        if not data.get("amount") or data["amount"] <= 0:
            errors.append("Amount is required and must be positive")

        if data.get("transaction_type") == "expense":
            if not data.get("vendor_name") and not data.get("category"):
                warnings.append("Vendor name not detected - you may want to specify the vendor")

        if data.get("confidence", 0) < 0.5:
            warnings.append("Low confidence extraction - please review all fields carefully")

        if data.get("missing_fields"):
            for field in data["missing_fields"]:
                warnings.append(f"Missing information: {field.replace('_', ' ')}")

        # Check if vendor exists in DB
        if data.get("vendor_name"):
            vendor = self.db.query(Vendor).filter(
                Vendor.company_id == uuid.UUID(company_id),
                Vendor.name.ilike(f"%{data['vendor_name']}%"),
                Vendor.is_active == True,
            ).first()
            if vendor:
                data["vendor_id"] = str(vendor.id)
                data["vendor_matched"] = vendor.name
            else:
                warnings.append(f"Vendor '{data['vendor_name']}' not found in your database - will be created as new")

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }
