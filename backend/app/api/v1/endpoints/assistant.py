import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin_or_accountant
from app.models.user import User
from app.models.company import Company
from app.models.ai_conversation import AIConversation, AIMessage, MessageRole
from app.models.customer import Customer
from app.models.vendor import Vendor
from app.models.product import Product
from app.models.expense import Expense, ExpenseStatus
from app.agents.transaction_agent import TransactionAgent
from app.agents.entity_agent import EntityAgent
from app.services.customer_service import customer_service
from app.services.vendor_service import vendor_service
from app.services.invoice_service import invoice_service
from app.services.tally_write_service import queue_tally_write
from app.schemas.customer import CustomerCreate
from app.schemas.vendor import VendorCreate
from app.schemas.invoice import InvoiceCreate, InvoiceItemCreate
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from app.tools.finance_tools import FinanceTools
from app.ai.tools.master_tools import MasterTools
from app.ai.tools.tally_tools import TallyTools
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)


def _parse_date(date_str) -> datetime:
    """
    Parse a date string in any common format into datetime.
    Handles: ISO (2026-08-01), YYYYMMDD (20260801), natural language
    (1 August 2026, August 1, 2026), DD/MM/YYYY, DD-MM-YYYY, etc.
    Falls back to today if nothing matches.
    """
    if not date_str:
        return datetime.now(timezone.utc)

    s = str(date_str).strip()

    # YYYYMMDD — 8 digits, no separators
    if len(s) == 8 and s.isdigit():
        try:
            return datetime.strptime(s, "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # ISO date — 2026-09-01 or 2026-09-01T...
    try:
        return datetime.fromisoformat(s[:10]).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass

    # Natural language and regional formats
    for fmt in (
        "%d %B %Y",   # 1 September 2026
        "%d %b %Y",   # 1 Sep 2026
        "%B %d, %Y",  # September 1, 2026
        "%b %d, %Y",  # Sep 1, 2026
        "%B %d %Y",   # September 1 2026
        "%d-%m-%Y",   # 01-09-2026
        "%d/%m/%Y",   # 01/09/2026
        "%m/%d/%Y",   # 09/01/2026
        "%d.%m.%Y",   # 01.09.2026
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    # Last resort: dateutil
    try:
        from dateutil import parser as du_parser
        return du_parser.parse(s, dayfirst=True).replace(tzinfo=timezone.utc)
    except Exception:
        pass

    return datetime.now(timezone.utc)

# Lazy import to avoid ImportError if langgraph not installed yet
def _run_graph_assistant(query, company_id, user_id, role, provider, history, db):
    try:
        from app.ai.graph.assistant_graph import run_assistant
        ft = FinanceTools(db)
        mt = MasterTools(db)
        tt = TallyTools(db)
        return run_assistant(query, company_id, user_id, role, provider, history, ft, mt, tt)
    except ImportError:
        # Fallback to legacy FinanceAgent if langgraph not installed
        logger.warning("langgraph not installed, falling back to FinanceAgent")
        from app.agents.finance_agent import FinanceAgent
        agent = FinanceAgent(db)
        return agent.chat(query, company_id, history, provider)

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"


class ConversationRename(BaseModel):
    title: str


class MessageCreate(BaseModel):
    content: str


class TransactionProposal(BaseModel):
    text: str


class EntityExtractRequest(BaseModel):
    text: str


class EntityCreateRequest(BaseModel):
    entity_type: str
    data: Dict[str, Any]


@router.get("/conversations")
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convs = db.query(AIConversation).filter(
        AIConversation.company_id == current_user.company_id,
        AIConversation.user_id == current_user.id,
        AIConversation.is_active == True,
    ).order_by(AIConversation.updated_at.desc()).all()

    return [
        {
            "id": str(c.id), "title": c.title,
            "created_at": c.created_at.isoformat(),
            "updated_at": c.updated_at.isoformat(),
        }
        for c in convs
    ]


@router.post("/conversations")
def create_conversation(
    data: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = AIConversation(
        company_id=current_user.company_id,
        user_id=current_user.id,
        title=data.title,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": str(conv.id), "title": conv.title, "created_at": conv.created_at.isoformat()}


@router.put("/conversations/{conv_id}")
def rename_conversation(
    conv_id: str,
    data: ConversationRename,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(AIConversation).filter(
        AIConversation.id == uuid.UUID(conv_id),
        AIConversation.user_id == current_user.id,
        AIConversation.company_id == current_user.company_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.title = data.title
    db.commit()
    return {"message": "Renamed"}


@router.delete("/conversations/{conv_id}")
def delete_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(AIConversation).filter(
        AIConversation.id == uuid.UUID(conv_id),
        AIConversation.user_id == current_user.id,
        AIConversation.company_id == current_user.company_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.is_active = False
    db.commit()
    return {"message": "Deleted"}


@router.get("/conversations/{conv_id}/messages")
def get_messages(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(AIConversation).filter(
        AIConversation.id == uuid.UUID(conv_id),
        AIConversation.user_id == current_user.id,
        AIConversation.company_id == current_user.company_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    messages = db.query(AIMessage).filter(
        AIMessage.conversation_id == conv.id
    ).order_by(AIMessage.created_at).all()

    return [
        {
            "id": str(m.id), "role": m.role.value, "content": m.content,
            "is_demo": m.is_demo, "created_at": m.created_at.isoformat(),
            "tool_calls": m.tool_calls, "tool_results": m.tool_results,
        }
        for m in messages
    ]


@router.post("/conversations/{conv_id}/messages")
def send_message(
    conv_id: str,
    data: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.query(AIConversation).filter(
        AIConversation.id == uuid.UUID(conv_id),
        AIConversation.user_id == current_user.id,
        AIConversation.company_id == current_user.company_id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save user message
    user_msg = AIMessage(
        conversation_id=conv.id,
        role=MessageRole.USER,
        content=data.content,
    )
    db.add(user_msg)
    db.commit()

    # Get conversation history for context
    history = db.query(AIMessage).filter(
        AIMessage.conversation_id == conv.id
    ).order_by(AIMessage.created_at).all()

    history_for_agent = [
        {"role": m.role.value, "content": m.content}
        for m in history[:-1]  # exclude the message we just added
    ]

    # Load company's provider preference
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    provider_override = company.ai_provider if company and company.ai_provider else None
    from app.core.config import settings
    effective_provider = provider_override or settings.AI_PROVIDER

    # Run LangGraph assistant (with fallback to legacy FinanceAgent)
    result = _run_graph_assistant(
        data.content,
        str(current_user.company_id),
        str(current_user.id),
        current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        effective_provider,
        history_for_agent,
        db,
    )

    # Save assistant message
    ai_msg = AIMessage(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=result["response"],
        is_demo=result["is_demo"],
        tool_calls=result.get("tool_calls"),
        tool_results=result.get("tool_results"),
    )
    db.add(ai_msg)

    # Auto-update conversation title on first message
    msg_count = db.query(AIMessage).filter(AIMessage.conversation_id == conv.id).count()
    if msg_count <= 2 and conv.title == "New Conversation":
        conv.title = data.content[:50] + ("..." if len(data.content) > 50 else "")

    db.commit()

    # Audit log
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.AI_QUERY,
                      description=f"AI query: {data.content[:100]}")

    return {
        "id": str(ai_msg.id),
        "role": "assistant",
        "content": result["response"],
        "is_demo": result["is_demo"],
        "provider": result.get("provider"),
        "error": result.get("error"),
        "tool_calls": result.get("tool_calls"),
        "created_at": ai_msg.created_at.isoformat(),
    }


@router.post("/propose-transaction")
def propose_transaction(
    data: TransactionProposal,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    agent = TransactionAgent(db)
    result = agent.propose(data.text, str(current_user.company_id))

    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.AI_PROPOSAL,
                      description=f"AI transaction proposal: {data.text[:100]}")

    return result


_STANDARD_TALLY_TYPES = {
    "sales", "purchase", "receipt", "payment", "contra", "journal",
    "credit note", "debit note", "sales order", "purchase order",
    "delivery note", "receipt note", "stock journal", "physical stock",
    "reversing journal", "memorandum", "attendance", "payroll",
    "material in", "material out", "rejections in", "rejections out",
    "job work in order", "job work out order",
}


def _detect_custom_voucher_type(text: str, company_id, db) -> dict | None:
    """
    Check if the text mentions a known custom voucher type from the DB.
    If yes, return the extraction result directly — bypasses the LLM.
    This is more reliable than prompt engineering for custom type detection.
    """
    from app.models.tally_masters import TallyVoucherType
    custom_types = db.query(TallyVoucherType).filter(
        TallyVoucherType.company_id == company_id,
        TallyVoucherType.is_active == True,
    ).all()

    text_lower = text.lower()
    # Check longest names first to avoid partial matches (e.g. "GST Bill" before "Bill")
    custom_types_sorted = sorted(
        [vt for vt in custom_types if vt.name.lower() not in _STANDARD_TALLY_TYPES],
        key=lambda v: len(v.name), reverse=True,
    )

    matched = None
    for vt in custom_types_sorted:
        if vt.name.lower() in text_lower:
            matched = vt
            break

    if not matched:
        return None

    import re
    # Extract amount
    amount_m = re.search(r'[₹]?\s*([\d,]+(?:\.\d+)?)', text)
    amount = amount_m.group(1).replace(',', '') if amount_m else "0"

    # Extract date (YYYY-MM-DD or natural language)
    date_m = re.search(r'(\d{4}-\d{2}-\d{2})', text)
    date_val = date_m.group(1) if date_m else ""
    if not date_val:
        # Natural language: "15 August 2026" / "1 September 2026"
        nat_m = re.search(r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})', text, re.IGNORECASE)
        if nat_m:
            months = {"january":"01","february":"02","march":"03","april":"04","may":"05","june":"06",
                      "july":"07","august":"08","september":"09","october":"10","november":"11","december":"12"}
            date_val = f"{nat_m.group(3)}-{months[nat_m.group(2).lower()]}-{nat_m.group(1).zfill(2)}"

    # Extract party — text after "for" but before "for ₹" / amount
    party = ""
    party_m = re.search(
        rf'for\s+([A-Za-z\s&\'.]+?)(?:\s+for\s+[₹\d]|\s+[₹]\s*[\d]|\s+dated|\s+on\s+\d|,|$)',
        text, re.IGNORECASE
    )
    if party_m:
        candidate = party_m.group(1).strip()
        # Discard if it looks like an amount
        if not re.match(r'^[\d₹,\.]+$', candidate):
            party = candidate

    # Extract narration
    narr_m = re.search(r'narration[:\s]+([^,\n]+)', text, re.IGNORECASE)
    narration = narr_m.group(1).strip() if narr_m else ""

    # Build payload based on parent type
    parent = (matched.parent or "Sales").strip()
    data_payload: dict = {
        "voucher_type_name": matched.name,
        "amount": amount,
        "narration": narration,
    }
    if date_val:
        data_payload["date"] = date_val
    if parent in ("Sales", "Credit Note"):
        data_payload["party_ledger"] = party
        data_payload["sales_ledger"] = "Sales"
    elif parent in ("Purchase", "Debit Note"):
        data_payload["party_ledger"] = party
        data_payload["purchase_ledger"] = "Purchases"
    elif parent in ("Receipt", "Payment"):
        data_payload["party_ledger"] = party
        data_payload["account_ledger"] = "Cash"
    elif parent == "Journal":
        data_payload["dr_ledger"] = ""
        data_payload["cr_ledger"] = ""
    else:
        data_payload["party_ledger"] = party

    missing = []
    if not party and parent not in ("Journal", "Contra"):
        missing.append("party_ledger")
    if not date_val:
        missing.append("date")

    return {
        "entity_type": "custom_voucher",
        "data": data_payload,
        "confidence": 0.95,
        "missing_fields": missing,
    }


_STOCK_TXN_ENTITY_TYPES = {
    "stock_journal", "physical_stock", "delivery_note",
    "receipt_note", "rejection_in", "rejection_out",
}


def _enrich_stock_txn_entries(result: dict, company_id, db) -> dict:
    """
    For stock transaction extractions, look up each entry's stock item
    in TallyStockItem and fill in the correct unit and rate so the
    preview shows real values before the user clicks Create.
    """
    from app.models.tally_masters import TallyStockItem as _TSI
    entries = result.get("data", {}).get("entries")
    if not isinstance(entries, list):
        return result

    missing = []
    enriched = []
    for e in entries:
        if not isinstance(e, dict):
            enriched.append(e)
            continue
        item_name = str(e.get("stock_item_name") or "").strip()
        unit  = str(e.get("unit") or "").strip()
        rate  = float(e.get("rate") or 0)

        if item_name and (not unit or rate == 0):
            si = db.query(_TSI).filter(
                _TSI.company_id == company_id,
                _TSI.name.ilike(item_name),
                _TSI.is_active == True,
            ).first()
            if si:
                if not unit:
                    unit = si.unit or ""
                if rate == 0 and si.rate:
                    rate = float(si.rate)
            elif item_name:
                missing.append(item_name)

        enriched.append({**e, "unit": unit, "rate": rate})

    result = {**result, "data": {**result.get("data", {}), "entries": enriched}}

    # Warn if any item name wasn't found in synced data
    if missing:
        existing_missing = list(result.get("missing_fields") or [])
        for m in missing:
            existing_missing.insert(0, f'"{m}" not found in synced stock items — verify the exact name in TallyPrime')
        result = {**result, "missing_fields": existing_missing}

    return result


@router.post("/extract-entity")
def extract_entity(
    data: EntityExtractRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Extract structured entity data from natural language using AI."""
    # DB-first: if text mentions a known custom voucher type, skip the LLM
    custom_result = _detect_custom_voucher_type(data.text, current_user.company_id, db)
    if custom_result:
        audit_service.log(db, current_user.company_id, current_user.id, AuditAction.AI_QUERY,
                          description=f"AI entity extraction (custom type match): {data.text[:100]}")
        return custom_result

    agent = EntityAgent()
    result = agent.extract(data.text)

    # For stock transaction types, enrich entries with unit/rate from synced TallyStockItem
    if result.get("entity_type") in _STOCK_TXN_ENTITY_TYPES:
        result = _enrich_stock_txn_entries(result, current_user.company_id, db)

    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.AI_QUERY,
                      description=f"AI entity extraction: {data.text[:100]}")

    return result


@router.post("/create-entity")
def create_entity(
    data: EntityCreateRequest,
    current_user: User = Depends(require_admin_or_accountant),
    db: Session = Depends(get_db),
):
    """Create an entity in FinPilot DB and queue a Tally write job."""
    entity_type = data.entity_type.lower()
    payload = data.data

    # Normalise generic "voucher" type the AI sometimes returns
    if entity_type == "voucher":
        vt = str(payload.get("voucher_type", "")).lower()
        entity_type = {
            "transfer": "contra", "contra": "contra",
            "receipt": "receipt", "payment": "payment",
            "journal": "journal", "jv": "journal",
            "credit note": "credit_note", "debit note": "debit_note",
            "sales": "sales_invoice", "purchase": "purchase_bill",
        }.get(vt, "journal")
    entity_id = None
    tally_queued = False

    try:
        if entity_type == "customer":
            create_data = CustomerCreate(
                name=payload.get("name", ""),
                email=payload.get("email"),
                phone=payload.get("phone"),
                address=payload.get("address"),
                city=payload.get("city"),
                state=payload.get("state"),
                gst_number=payload.get("gstin") or payload.get("gst_number"),
                notes=payload.get("notes"),
            )
            entity = customer_service.create(db, current_user.company_id, create_data)
            entity_id = str(entity.id)
            tally_queued = queue_tally_write(
                db, current_user.company_id, "CREATE_LEDGER",
                {"name": entity.name, "group": "Sundry Debtors", "opening_balance": "0"},
            )
            if tally_queued:
                db.commit()

        elif entity_type == "vendor":
            create_data = VendorCreate(
                name=payload.get("name", ""),
                email=payload.get("email"),
                phone=payload.get("phone"),
                address=payload.get("address"),
                city=payload.get("city"),
                state=payload.get("state"),
                gst_number=payload.get("gstin") or payload.get("gst_number"),
                notes=payload.get("notes"),
            )
            entity = vendor_service.create(db, current_user.company_id, create_data)
            entity_id = str(entity.id)
            tally_queued = queue_tally_write(
                db, current_user.company_id, "CREATE_LEDGER",
                {"name": entity.name, "group": "Sundry Creditors", "opening_balance": "0"},
            )
            if tally_queued:
                db.commit()

        elif entity_type == "product":
            product = Product(
                company_id=current_user.company_id,
                name=payload.get("name", ""),
                sku=payload.get("sku"),
                selling_price=float(payload.get("selling_price") or 0),
                purchase_price=float(payload.get("cost_price") or 0),
                unit=payload.get("unit", "pcs"),
                stock_quantity=float(payload.get("quantity") or 0),
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            entity_id = str(product.id)
            tally_queued = queue_tally_write(
                db, current_user.company_id, "CREATE_STOCK_ITEM",
                {
                    "name": product.name,
                    "unit": product.unit,
                    "rate": str(int(float(product.selling_price or 0))),
                },
            )
            if tally_queued:
                db.commit()

        elif entity_type == "invoice":
            customer_id = payload.get("customer_id")
            vendor_id = payload.get("vendor_id")
            invoice_type = payload.get("invoice_type", "SALES").upper()

            # Normalise: AI may use customer_name OR party_ledger for the party field
            _cust_name = payload.get("customer_name") or payload.get("party_ledger") or payload.get("party", "")
            _vend_name = payload.get("vendor_name") or payload.get("party_ledger") or payload.get("party", "")
            if _cust_name:
                payload["customer_name"] = _cust_name
            if _vend_name:
                payload["vendor_name"] = _vend_name

            if not customer_id and _cust_name and invoice_type == "SALES":
                cust = db.query(Customer).filter(
                    Customer.company_id == current_user.company_id,
                    Customer.name.ilike(f"%{_cust_name}%"),
                    Customer.is_active == True,
                ).first()
                if cust:
                    customer_id = str(cust.id)

            if not vendor_id and _vend_name and invoice_type == "PURCHASE":
                vend = db.query(Vendor).filter(
                    Vendor.company_id == current_user.company_id,
                    Vendor.name.ilike(f"%{_vend_name}%"),
                    Vendor.is_active == True,
                ).first()
                if vend:
                    vendor_id = str(vend.id)

            amount = float(payload.get("amount") or 0)
            inv_date = _parse_date(payload.get("date", ""))

            create_data = InvoiceCreate(
                customer_id=customer_id,
                vendor_id=vendor_id,
                invoice_number=payload.get("narration") or f"AI-{uuid.uuid4().hex[:8].upper()}",
                invoice_type=invoice_type,
                invoice_date=inv_date,
                items=[
                    InvoiceItemCreate(
                        description=payload.get("narration") or "AI-created item",
                        quantity=1,
                        unit_price=amount,
                    )
                ] if amount else [],
            )
            entity = invoice_service.create(db, current_user.company_id, current_user.id, create_data)
            entity_id = str(entity.id)

            tally_date = entity.invoice_date.strftime("%Y%m%d")
            amount_str = str(int(float(entity.total_amount)))
            # Pre-generate REMOTEID so we can cancel later by this ref
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            if invoice_type == "SALES":
                # AI may extract customer name as customer_name OR party_ledger — accept both
                party_name = (
                    payload.get("customer_name")
                    or payload.get("party_ledger")
                    or payload.get("party", "")
                )
                sales_ledger = payload.get("sales_ledger") or "Sales"
                tally_queued = queue_tally_write(
                    db, current_user.company_id, "CREATE_SALES_VOUCHER",
                    {"date": tally_date, "party_ledger": party_name,
                     "sales_ledger": sales_ledger, "amount": amount_str,
                     "narration": entity.invoice_number, "voucher_number": vnum},
                )
            else:
                # AI may extract vendor name as vendor_name OR party_ledger — accept both
                party_name = (
                    payload.get("vendor_name")
                    or payload.get("party_ledger")
                    or payload.get("party", "")
                )
                purchase_ledger = payload.get("purchase_ledger") or "Purchases"
                tally_queued = queue_tally_write(
                    db, current_user.company_id, "CREATE_PURCHASE_VOUCHER",
                    {"date": tally_date, "party_ledger": party_name,
                     "purchase_ledger": purchase_ledger, "amount": amount_str,
                     "narration": entity.invoice_number, "voucher_number": vnum},
                )
            if tally_queued:
                # Store ref so we can cancel later
                entity.tally_voucher_ref = vnum
                entity.tally_sync_status = "pending"
                db.commit()

        elif entity_type == "expense":
            exp_date = _parse_date(payload.get("date", ""))

            vendor_id = payload.get("vendor_id")
            if not vendor_id and payload.get("vendor_name"):
                vend = db.query(Vendor).filter(
                    Vendor.company_id == current_user.company_id,
                    Vendor.name.ilike(f"%{payload['vendor_name']}%"),
                    Vendor.is_active == True,
                ).first()
                if vend:
                    vendor_id = str(vend.id)

            amount = float(payload.get("amount") or 0)
            expense = Expense(
                company_id=current_user.company_id,
                created_by=current_user.id,
                vendor_id=uuid.UUID(vendor_id) if vendor_id else None,
                title=payload.get("title", "AI-created expense"),
                description=payload.get("description"),
                category=payload.get("category"),
                expense_date=exp_date,
                amount=amount,
                tax_amount=0,
                total_amount=amount,
                status=ExpenseStatus.DRAFT,
            )
            db.add(expense)
            db.commit()
            db.refresh(expense)
            entity_id = str(expense.id)

            vendor_name = payload.get("vendor_name", "Cash")
            vnum_exp = f"FP-{uuid.uuid4().hex[:12].upper()}"
            tally_queued = queue_tally_write(
                db, current_user.company_id, "CREATE_PAYMENT_VOUCHER",
                {
                    "date": exp_date.strftime("%Y%m%d"),
                    "party_ledger": vendor_name,
                    "account_ledger": payload.get("account_ledger", "Cash"),
                    "amount": str(int(amount)),
                    "narration": expense.title,
                    "voucher_number": vnum_exp,
                },
            )
            if tally_queued:
                expense.tally_voucher_ref = vnum_exp
                expense.tally_sync_status = "pending"
                db.commit()

        elif entity_type == "stock_item":
            from app.models.tally_masters import TallyStockItem
            from app.models.tally_connector import TallyConnector, ConnectorStatus
            from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
            si_name = (payload.get("name") or "").strip()
            if not si_name:
                raise HTTPException(status_code=422, detail="Stock item name is required")
            si_key = f"{current_user.company_id}::{si_name.strip().lower()}"
            existing_si = db.query(TallyStockItem).filter(
                TallyStockItem.company_id == current_user.company_id,
                TallyStockItem.tally_key == si_key,
                TallyStockItem.is_active == True,
            ).first()
            if existing_si:
                raise HTTPException(status_code=409, detail=f"Stock item '{si_name}' already exists")
            si_rate = float(payload.get("rate") or payload.get("selling_price") or 0)
            si_qty = float(payload.get("opening_qty") or payload.get("quantity") or 0)
            si_group = (payload.get("stock_group") or "").strip() or None
            si_unit = (payload.get("unit") or "Nos").strip()
            record = TallyStockItem(
                company_id=current_user.company_id,
                name=si_name, stock_group=si_group, unit=si_unit,
                rate=si_rate, opening_qty=si_qty,
                tally_key=si_key, source="finpilot", tally_sync_status="pending",
            )
            db.add(record)
            db.flush()
            connector = db.query(TallyConnector).filter(
                TallyConnector.company_id == current_user.company_id,
                TallyConnector.status == ConnectorStatus.ACTIVE,
            ).first()
            if connector:
                job_payload = {"name": si_name, "unit": si_unit, "rate": str(si_rate), "opening_qty": str(si_qty)}
                if si_group:
                    job_payload["stock_group"] = si_group
                job = TallyIntegrationJob(
                    company_id=current_user.company_id, connector_id=connector.id,
                    created_by=current_user.id, operation=TallyJobOperation.CREATE_STOCK_ITEM,
                    payload=job_payload, idempotency_key=f"create_stock_item::{record.id}",
                )
                db.add(job)
                db.flush()
                record.tally_job_id = job.id
                tally_queued = True
            entity_id = str(record.id)
            db.commit()

        elif entity_type == "sales_invoice":
            payload["invoice_type"] = "SALES"
            payload["customer_name"] = payload.get("customer_name", "")
            return create_entity(EntityCreateRequest(entity_type="invoice", data=payload),
                                 current_user, db)

        elif entity_type == "purchase_bill":
            payload["invoice_type"] = "PURCHASE"
            payload["vendor_name"] = payload.get("vendor_name", "")
            return create_entity(EntityCreateRequest(entity_type="invoice", data=payload),
                                 current_user, db)

        # Tally master entities — save to FinPilot DB so management pages show them,
        # then queue the job so the connector pushes them to TallyPrime.
        elif entity_type == "ledger":
            from app.models.tally_masters import TallyLedger
            from app.models.tally_connector import TallyConnector, ConnectorStatus
            from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
            name = (payload.get("name") or "").strip()
            group = payload.get("group") or "Sundry Debtors"
            opening_balance = float(payload.get("opening_balance") or 0)
            tally_key = f"{current_user.company_id}::{name.lower()}"
            existing = db.query(TallyLedger).filter(
                TallyLedger.company_id == current_user.company_id,
                TallyLedger.tally_key == tally_key,
                TallyLedger.is_active == True,
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"Ledger '{name}' already exists")
            record = TallyLedger(
                company_id=current_user.company_id,
                name=name, parent_group=group,
                opening_balance=opening_balance,
                tally_key=tally_key, source="finpilot", tally_sync_status="pending",
            )
            db.add(record)
            db.flush()
            connector = db.query(TallyConnector).filter(
                TallyConnector.company_id == current_user.company_id,
                TallyConnector.status == ConnectorStatus.ACTIVE,
            ).first()
            if connector:
                job = TallyIntegrationJob(
                    company_id=current_user.company_id, connector_id=connector.id,
                    created_by=current_user.id, operation=TallyJobOperation.CREATE_LEDGER,
                    payload={"name": name, "group": group, "opening_balance": str(int(opening_balance))},
                    idempotency_key=f"create_ledger::{record.id}",
                )
                db.add(job)
                db.flush()
                record.tally_job_id = job.id
                tally_queued = True
            entity_id = str(record.id)
            db.commit()

        elif entity_type == "group":
            from app.models.tally_masters import TallyGroup
            from app.models.tally_connector import TallyConnector, ConnectorStatus
            from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
            name = (payload.get("name") or "").strip()
            parent = (payload.get("parent") or "").strip() or None
            nature = (payload.get("nature") or "").strip() or None
            tally_key = f"{current_user.company_id}::{name.lower()}"
            existing = db.query(TallyGroup).filter(
                TallyGroup.company_id == current_user.company_id,
                TallyGroup.tally_key == tally_key,
                TallyGroup.is_active == True,
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"Account group '{name}' already exists")
            record = TallyGroup(
                company_id=current_user.company_id,
                name=name, parent=parent, nature=nature,
                tally_key=tally_key, source="finpilot", tally_sync_status="pending",
            )
            db.add(record)
            db.flush()
            connector = db.query(TallyConnector).filter(
                TallyConnector.company_id == current_user.company_id,
                TallyConnector.status == ConnectorStatus.ACTIVE,
            ).first()
            if connector:
                job_payload = {"name": name}
                if parent:
                    job_payload["parent"] = parent
                job = TallyIntegrationJob(
                    company_id=current_user.company_id, connector_id=connector.id,
                    created_by=current_user.id, operation=TallyJobOperation.CREATE_GROUP,
                    payload=job_payload, idempotency_key=f"create_group::{record.id}",
                )
                db.add(job)
                db.flush()
                record.tally_job_id = job.id
                tally_queued = True
            entity_id = str(record.id)
            db.commit()

        elif entity_type == "stock_group":
            from app.models.tally_masters import TallyStockGroup
            from app.models.tally_connector import TallyConnector, ConnectorStatus
            from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
            name = (payload.get("name") or "").strip()
            sg_parent = (payload.get("parent") or "").strip()
            if sg_parent.lower() in ("primary", ""):
                sg_parent = ""
            tally_key = f"{current_user.company_id}::{name.lower()}"
            existing = db.query(TallyStockGroup).filter(
                TallyStockGroup.company_id == current_user.company_id,
                TallyStockGroup.tally_key == tally_key,
                TallyStockGroup.is_active == True,
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"Stock group '{name}' already exists")
            record = TallyStockGroup(
                company_id=current_user.company_id,
                name=name, parent=sg_parent or None,
                tally_key=tally_key, source="finpilot", tally_sync_status="pending",
            )
            db.add(record)
            db.flush()
            connector = db.query(TallyConnector).filter(
                TallyConnector.company_id == current_user.company_id,
                TallyConnector.status == ConnectorStatus.ACTIVE,
            ).first()
            if connector:
                job_payload = {"name": name}
                if sg_parent:
                    job_payload["parent"] = sg_parent
                job = TallyIntegrationJob(
                    company_id=current_user.company_id, connector_id=connector.id,
                    created_by=current_user.id, operation=TallyJobOperation.CREATE_STOCK_GROUP,
                    payload=job_payload, idempotency_key=f"create_stock_group::{record.id}",
                )
                db.add(job)
                db.flush()
                record.tally_job_id = job.id
                tally_queued = True
            entity_id = str(record.id)
            db.commit()

        elif entity_type == "unit":
            from app.models.tally_masters import TallyUnit
            from app.models.tally_connector import TallyConnector, ConnectorStatus
            from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
            name = (payload.get("name") or "").strip()
            symbol = (payload.get("symbol") or name).strip().replace(" ", "")[:8] or name[:8]
            decimal_places = int(payload.get("decimal_places") or 0)
            tally_key = f"{current_user.company_id}::{name.lower()}"
            existing = db.query(TallyUnit).filter(
                TallyUnit.company_id == current_user.company_id,
                TallyUnit.tally_key == tally_key,
                TallyUnit.is_active == True,
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"Unit '{name}' already exists")
            record = TallyUnit(
                company_id=current_user.company_id,
                name=name, symbol=symbol, decimal_places=decimal_places, unit_type="simple",
                tally_key=tally_key, source="finpilot", tally_sync_status="pending",
            )
            db.add(record)
            db.flush()
            connector = db.query(TallyConnector).filter(
                TallyConnector.company_id == current_user.company_id,
                TallyConnector.status == ConnectorStatus.ACTIVE,
            ).first()
            if connector:
                job = TallyIntegrationJob(
                    company_id=current_user.company_id, connector_id=connector.id,
                    created_by=current_user.id, operation=TallyJobOperation.CREATE_UNIT,
                    payload={"name": name, "symbol": symbol, "decimal_places": str(decimal_places)},
                    idempotency_key=f"create_unit::{record.id}",
                )
                db.add(job)
                db.flush()
                record.tally_job_id = job.id
                tally_queued = True
            entity_id = str(record.id)
            db.commit()

        elif entity_type == "godown":
            from app.models.tally_masters import TallyGodown
            from app.models.tally_connector import TallyConnector, ConnectorStatus
            from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
            name = (payload.get("name") or "").strip()
            gd_parent = (payload.get("parent") or "").strip()
            if gd_parent.lower() in ("main location", "primary", ""):
                gd_parent = ""
            tally_key = f"{current_user.company_id}::{name.lower()}"
            existing = db.query(TallyGodown).filter(
                TallyGodown.company_id == current_user.company_id,
                TallyGodown.tally_key == tally_key,
                TallyGodown.is_active == True,
            ).first()
            if existing:
                raise HTTPException(status_code=409, detail=f"Godown '{name}' already exists")
            record = TallyGodown(
                company_id=current_user.company_id,
                name=name, parent=gd_parent or None,
                tally_key=tally_key, source="finpilot", tally_sync_status="pending",
            )
            db.add(record)
            db.flush()
            connector = db.query(TallyConnector).filter(
                TallyConnector.company_id == current_user.company_id,
                TallyConnector.status == ConnectorStatus.ACTIVE,
            ).first()
            if connector:
                job_payload = {"name": name}
                if gd_parent:
                    job_payload["parent"] = gd_parent
                job = TallyIntegrationJob(
                    company_id=current_user.company_id, connector_id=connector.id,
                    created_by=current_user.id, operation=TallyJobOperation.CREATE_GODOWN,
                    payload=job_payload, idempotency_key=f"create_godown::{record.id}",
                )
                db.add(job)
                db.flush()
                record.tally_job_id = job.id
                tally_queued = True
            entity_id = str(record.id)
            db.commit()

        elif entity_type == "receipt":
            d = _parse_date(payload.get("date", ""))
            amount = float(payload.get("amount", 0))
            narration = payload.get("narration", "Receipt")
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            record = Expense(
                company_id=current_user.company_id, created_by=current_user.id,
                title=narration or "Receipt", category="Receipt",
                expense_date=d, amount=amount, tax_amount=0, total_amount=amount,
                currency="INR", status=ExpenseStatus.APPROVED,
                notes=f"Party: {payload.get('party_ledger', '')} | Account: {payload.get('account_ledger', 'Cash')}",
                tally_sync_status="pending", tally_voucher_ref=vnum,
            )
            db.add(record)
            db.flush()
            entity_id = str(record.id)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_RECEIPT_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "account_ledger": payload.get("account_ledger", "Cash"),
                 "amount": str(int(amount)), "narration": narration, "voucher_number": vnum})
            if tally_queued: db.commit()

        elif entity_type == "payment":
            d = _parse_date(payload.get("date", ""))
            amount = float(payload.get("amount", 0))
            narration = payload.get("narration", "Payment")
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            record = Expense(
                company_id=current_user.company_id, created_by=current_user.id,
                title=narration or "Payment", category="Payment",
                expense_date=d, amount=amount, tax_amount=0, total_amount=amount,
                currency="INR", status=ExpenseStatus.APPROVED,
                notes=f"Party: {payload.get('party_ledger', '')} | Account: {payload.get('account_ledger', 'Cash')}",
                tally_sync_status="pending", tally_voucher_ref=vnum,
            )
            db.add(record)
            db.flush()
            entity_id = str(record.id)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_PAYMENT_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "account_ledger": payload.get("account_ledger", "Cash"),
                 "amount": str(int(amount)), "narration": narration, "voucher_number": vnum})
            if tally_queued: db.commit()

        elif entity_type == "journal":
            d = _parse_date(payload.get("date", ""))
            amount = float(payload.get("amount", 0))
            narration = payload.get("narration", "Journal Entry")
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            record = Expense(
                company_id=current_user.company_id, created_by=current_user.id,
                title=narration or "Journal Entry", category="Journal",
                expense_date=d, amount=amount, tax_amount=0, total_amount=amount,
                currency="INR", status=ExpenseStatus.APPROVED,
                notes=f"Dr: {payload.get('dr_ledger', '')} | Cr: {payload.get('cr_ledger', '')}",
                tally_sync_status="pending", tally_voucher_ref=vnum,
            )
            db.add(record)
            db.flush()
            entity_id = str(record.id)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_JOURNAL_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "dr_ledger": payload.get("dr_ledger", ""),
                 "cr_ledger": payload.get("cr_ledger", ""),
                 "amount": str(int(amount)), "narration": narration, "voucher_number": vnum})
            if tally_queued: db.commit()

        elif entity_type == "credit_note":
            d = _parse_date(payload.get("date", ""))
            amount = float(payload.get("amount", 0))
            narration = payload.get("narration", "Sales Return")
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            record = Expense(
                company_id=current_user.company_id, created_by=current_user.id,
                title=narration or "Sales Return", category="Credit Note",
                expense_date=d, amount=amount, tax_amount=0, total_amount=amount,
                currency="INR", status=ExpenseStatus.APPROVED,
                notes=f"Party: {payload.get('party_ledger', '')}",
                tally_sync_status="pending", tally_voucher_ref=vnum,
            )
            db.add(record)
            db.flush()
            entity_id = str(record.id)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_CREDIT_NOTE",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "sales_ledger": payload.get("sales_ledger", "Sales"),
                 "amount": str(int(amount)), "narration": narration, "voucher_number": vnum})
            if tally_queued: db.commit()

        elif entity_type == "debit_note":
            d = _parse_date(payload.get("date", ""))
            amount = float(payload.get("amount", 0))
            narration = payload.get("narration", "Purchase Return")
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            record = Expense(
                company_id=current_user.company_id, created_by=current_user.id,
                title=narration or "Purchase Return", category="Debit Note",
                expense_date=d, amount=amount, tax_amount=0, total_amount=amount,
                currency="INR", status=ExpenseStatus.APPROVED,
                notes=f"Party: {payload.get('party_ledger', '')}",
                tally_sync_status="pending", tally_voucher_ref=vnum,
            )
            db.add(record)
            db.flush()
            entity_id = str(record.id)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_DEBIT_NOTE",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "purchase_ledger": payload.get("purchase_ledger", "Purchases"),
                 "amount": str(int(amount)), "narration": narration, "voucher_number": vnum})
            if tally_queued: db.commit()

        elif entity_type == "contra":
            d = _parse_date(payload.get("date", ""))
            amount = float(payload.get("amount", 0))
            narration = payload.get("narration", "Fund Transfer")
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            record = Expense(
                company_id=current_user.company_id, created_by=current_user.id,
                title=narration or "Fund Transfer", category="Contra",
                expense_date=d, amount=amount, tax_amount=0, total_amount=amount,
                currency="INR", status=ExpenseStatus.APPROVED,
                notes=f"From: {payload.get('from_account', 'Cash')} | To: {payload.get('to_account', 'Bank')}",
                tally_sync_status="pending", tally_voucher_ref=vnum,
            )
            db.add(record)
            db.flush()
            entity_id = str(record.id)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_CONTRA_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "from_account": payload.get("from_account", "Cash"),
                 "to_account": payload.get("to_account", "Bank"),
                 "amount": str(int(amount)), "narration": narration, "voucher_number": vnum})
            if tally_queued: db.commit()

        elif entity_type == "custom_voucher":
            from app.models.tally_masters import TallyVoucherType
            vt_name = (payload.get("voucher_type_name") or "").strip()
            if not vt_name:
                raise HTTPException(status_code=422, detail="voucher_type_name is required for custom_voucher")
            vt_record = db.query(TallyVoucherType).filter(
                TallyVoucherType.company_id == current_user.company_id,
                TallyVoucherType.name.ilike(vt_name),
                TallyVoucherType.is_active == True,
            ).first()
            if not vt_record:
                raise HTTPException(
                    status_code=404,
                    detail=f"Custom voucher type '{vt_name}' not found. Create it first from Accounting → Voucher Types.",
                )
            parent = (vt_record.parent or "Sales").strip()
            d = _parse_date(payload.get("date", ""))
            amount = float(payload.get("amount", 0))
            narration = payload.get("narration", vt_name)
            vnum = f"FP-{uuid.uuid4().hex[:12].upper()}"
            record = Expense(
                company_id=current_user.company_id, created_by=current_user.id,
                title=narration or vt_name, category=vt_record.name,
                expense_date=d, amount=amount, tax_amount=0, total_amount=amount,
                currency="INR", status=ExpenseStatus.APPROVED,
                notes=f"Party: {payload.get('party_ledger', '')} | Type: {vt_record.name}",
                tally_sync_status="pending", tally_voucher_ref=vnum,
            )
            db.add(record)
            db.flush()
            entity_id = str(record.id)
            # Map parent → Tally operation and ledger fields
            _parent_op = {
                "Sales":       ("CREATE_SALES_VOUCHER",    {"party_ledger": payload.get("party_ledger", ""), "sales_ledger": payload.get("sales_ledger", "Sales")}),
                "Purchase":    ("CREATE_PURCHASE_VOUCHER", {"party_ledger": payload.get("party_ledger", ""), "purchase_ledger": payload.get("purchase_ledger", "Purchases")}),
                "Receipt":     ("CREATE_RECEIPT_VOUCHER",  {"party_ledger": payload.get("party_ledger", ""), "account_ledger": payload.get("account_ledger", "Cash")}),
                "Payment":     ("CREATE_PAYMENT_VOUCHER",  {"party_ledger": payload.get("party_ledger", ""), "account_ledger": payload.get("account_ledger", "Cash")}),
                "Journal":     ("CREATE_JOURNAL_VOUCHER",  {"dr_ledger": payload.get("dr_ledger", ""), "cr_ledger": payload.get("cr_ledger", "")}),
                "Contra":      ("CREATE_CONTRA_VOUCHER",   {"from_account": payload.get("from_account", "Cash"), "to_account": payload.get("to_account", "Bank")}),
                "Credit Note": ("CREATE_CREDIT_NOTE",      {"party_ledger": payload.get("party_ledger", ""), "sales_ledger": payload.get("sales_ledger", "Sales")}),
                "Debit Note":  ("CREATE_DEBIT_NOTE",       {"party_ledger": payload.get("party_ledger", ""), "purchase_ledger": payload.get("purchase_ledger", "Purchases")}),
            }
            operation, extra = _parent_op.get(parent, _parent_op["Sales"])
            tally_queued = queue_tally_write(db, current_user.company_id, operation, {
                "date": d.strftime("%Y%m%d"), "amount": str(int(amount)),
                "narration": narration, "voucher_number": vnum,
                "voucher_type_name": vt_record.name,  # tells tally_client to use custom type
                **extra,
            })
            if tally_queued: db.commit()

        elif entity_type in ("stock_journal", "physical_stock", "delivery_note", "receipt_note", "rejection_in", "rejection_out"):
            from app.models.stock_transaction import StockTransaction
            from app.models.tally_connector import TallyConnector, ConnectorStatus
            from app.models.tally_job import TallyIntegrationJob, TallyJobOperation
            import json as _json

            _ENTITY_TO_TXN = {
                "stock_journal":  "STOCK_JOURNAL",
                "physical_stock": "PHYSICAL_STOCK",
                "delivery_note":  "DELIVERY_NOTE",
                "receipt_note":   "RECEIPT_NOTE",
                "rejection_in":   "REJECTION_IN",
                "rejection_out":  "REJECTION_OUT",
            }
            _TYPE_TO_OP = {
                "STOCK_JOURNAL":  TallyJobOperation.CREATE_STOCK_JOURNAL,
                "PHYSICAL_STOCK": TallyJobOperation.CREATE_PHYSICAL_STOCK,
                "DELIVERY_NOTE":  TallyJobOperation.CREATE_DELIVERY_NOTE,
                "RECEIPT_NOTE":   TallyJobOperation.CREATE_RECEIPT_NOTE,
                "REJECTION_IN":   TallyJobOperation.CREATE_REJECTION_IN,
                "REJECTION_OUT":  TallyJobOperation.CREATE_REJECTION_OUT,
            }
            _PREFIXES = {
                "STOCK_JOURNAL": "SJ", "PHYSICAL_STOCK": "PS",
                "DELIVERY_NOTE": "DN", "RECEIPT_NOTE": "RN",
                "REJECTION_IN": "RI", "REJECTION_OUT": "RO",
            }

            txn_type = _ENTITY_TO_TXN[entity_type]

            # Parse entries — AI may return list, JSON string, or flat fields
            raw_entries = payload.get("entries") or []
            if isinstance(raw_entries, str):
                try:
                    raw_entries = _json.loads(raw_entries)
                except Exception:
                    raw_entries = []
            if not isinstance(raw_entries, list):
                raw_entries = []

            # Fallback: build a single entry from flat fields if entries is empty
            if not raw_entries and payload.get("stock_item_name"):
                raw_entries = [{
                    "stock_item_name": payload.get("stock_item_name", ""),
                    "quantity":        float(payload.get("quantity") or 1),
                    "unit":            payload.get("unit") or "Nos",
                    "rate":            float(payload.get("rate") or 0),
                    "godown":          payload.get("godown") or "",
                }]

            from app.models.tally_masters import TallyStockItem as _TSI

            entries = []
            for e in raw_entries:
                if not isinstance(e, dict):
                    continue
                item_name = str(e.get("stock_item_name") or "").strip()
                unit      = str(e.get("unit") or "").strip()
                rate      = float(e.get("rate") or 0)

                # Auto-fill unit and rate from synced TallyStockItem if not provided
                if item_name and (not unit or rate == 0):
                    si = db.query(_TSI).filter(
                        _TSI.company_id == current_user.company_id,
                        _TSI.name.ilike(item_name),
                        _TSI.is_active == True,
                    ).first()
                    if si:
                        if not unit:
                            unit = si.unit or ""
                        if rate == 0 and si.rate:
                            rate = float(si.rate)

                entries.append({
                    "stock_item_name": item_name,
                    "quantity":        float(e.get("quantity") or 1),
                    "unit":            unit,
                    "rate":            rate,
                    "godown":          str(e.get("godown") or ""),
                })

            d = _parse_date(payload.get("date", ""))
            txn_number = f"{_PREFIXES[txn_type]}-{uuid.uuid4().hex[:8].upper()}"

            txn = StockTransaction(
                company_id=current_user.company_id,
                created_by=current_user.id,
                transaction_number=txn_number,
                transaction_type=txn_type,
                transaction_date=d,
                narration=payload.get("narration") or None,
                party_name=payload.get("party_name") or None,
                from_godown=payload.get("from_godown") or None,
                to_godown=payload.get("to_godown") or None,
                entries=entries,
                tally_sync_status="local_only",
            )
            db.add(txn)
            db.flush()

            connector = db.query(TallyConnector).filter(
                TallyConnector.company_id == current_user.company_id,
                TallyConnector.status == ConnectorStatus.ACTIVE,
            ).first()

            if connector:
                date_str = txn.transaction_date.strftime("%Y%m%d") if txn.transaction_date else ""
                job = TallyIntegrationJob(
                    company_id=current_user.company_id,
                    connector_id=connector.id,
                    created_by=current_user.id,
                    operation=_TYPE_TO_OP[txn_type],
                    payload={
                        "transaction_number": txn.transaction_number,
                        "transaction_type":   txn.transaction_type,
                        "date":               date_str,
                        "narration":          txn.narration or "",
                        "party_name":         txn.party_name or "",
                        "from_godown":        txn.from_godown or "",
                        "to_godown":          txn.to_godown or "",
                        "entries":            txn.entries or [],
                    },
                    idempotency_key=f"create_stock_txn::{txn.id}",
                )
                db.add(job)
                db.flush()
                txn.tally_job_id = job.id
                txn.tally_sync_status = "pending"
                tally_queued = True

            entity_id = str(txn.id)
            db.commit()

        else:
            raise HTTPException(status_code=400, detail=f"Unknown entity_type: {entity_type}")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create entity: {str(e)}")

    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.CREATE,
                      entity_type=entity_type, entity_id=uuid.UUID(entity_id) if entity_id else None,
                      description=f"AI-created {entity_type}")

    return {
        "id": entity_id,
        "entity_type": entity_type,
        "tally_queued": tally_queued,
    }
