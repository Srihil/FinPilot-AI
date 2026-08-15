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


@router.post("/extract-entity")
def extract_entity(
    data: EntityExtractRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Extract structured entity data from natural language using AI."""
    agent = EntityAgent()
    result = agent.extract(data.text)

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
            # Find customer if customer_name is given
            customer_id = payload.get("customer_id")
            vendor_id = payload.get("vendor_id")
            invoice_type = payload.get("invoice_type", "SALES").upper()

            if not customer_id and payload.get("customer_name") and invoice_type == "SALES":
                cust = db.query(Customer).filter(
                    Customer.company_id == current_user.company_id,
                    Customer.name.ilike(f"%{payload['customer_name']}%"),
                    Customer.is_active == True,
                ).first()
                if cust:
                    customer_id = str(cust.id)

            if not vendor_id and payload.get("vendor_name") and invoice_type == "PURCHASE":
                vend = db.query(Vendor).filter(
                    Vendor.company_id == current_user.company_id,
                    Vendor.name.ilike(f"%{payload['vendor_name']}%"),
                    Vendor.is_active == True,
                ).first()
                if vend:
                    vendor_id = str(vend.id)

            amount = float(payload.get("amount") or 0)
            invoice_date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try:
                inv_date = datetime.fromisoformat(invoice_date_str)
            except Exception:
                inv_date = datetime.now(timezone.utc)

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
                party_name = payload.get("customer_name", "")
                tally_queued = queue_tally_write(
                    db, current_user.company_id, "CREATE_SALES_VOUCHER",
                    {"date": tally_date, "party_ledger": party_name,
                     "sales_ledger": "Sales", "amount": amount_str,
                     "narration": entity.invoice_number, "voucher_number": vnum},
                )
            else:
                party_name = payload.get("vendor_name", "")
                tally_queued = queue_tally_write(
                    db, current_user.company_id, "CREATE_PURCHASE_VOUCHER",
                    {"date": tally_date, "party_ledger": party_name,
                     "purchase_ledger": "Purchases", "amount": amount_str,
                     "narration": entity.invoice_number, "voucher_number": vnum},
                )
            if tally_queued:
                # Store ref so we can cancel later
                entity.tally_voucher_ref = vnum
                entity.tally_sync_status = "pending"
                db.commit()

        elif entity_type == "expense":
            expense_date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try:
                exp_date = datetime.fromisoformat(expense_date_str)
            except Exception:
                exp_date = datetime.now(timezone.utc)

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
                db, current_user.company_id, "CREATE_PURCHASE_VOUCHER",
                {
                    "date": exp_date.strftime("%Y%m%d"),
                    "party_ledger": vendor_name,
                    "purchase_ledger": "Purchases",
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
            product = Product(
                company_id=current_user.company_id,
                name=payload.get("name", ""),
                sku=payload.get("sku"),
                selling_price=float(payload.get("selling_price") or 0),
                purchase_price=float(payload.get("cost_price") or 0),
                unit=payload.get("unit", "Nos"),
                stock_quantity=float(payload.get("quantity") or 0),
            )
            db.add(product)
            db.commit()
            db.refresh(product)
            entity_id = str(product.id)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_STOCK_ITEM",
                {"name": product.name, "unit": product.unit,
                 "selling_price": str(int(float(product.selling_price or 0))),
                 "stock_group": payload.get("stock_group", "Primary")})
            if tally_queued: db.commit()

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

        # TallyPrime-only entities (no FinPilot DB model — just queue write job)
        elif entity_type == "ledger":
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_LEDGER",
                {"name": payload.get("name", ""), "group": payload.get("group", "Sundry Debtors"),
                 "opening_balance": str(payload.get("opening_balance", "0"))})
            if tally_queued: db.commit()

        elif entity_type == "group":
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_GROUP",
                {"name": payload.get("name", ""), "parent": payload.get("parent", "Capital Account")})
            if tally_queued: db.commit()

        elif entity_type == "stock_group":
            sg_parent = (payload.get("parent") or "").strip()
            # Strip "Primary" — TallyPrime's implicit root cannot be referenced by name
            if sg_parent.lower() in ("primary", ""):
                sg_parent = ""
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_STOCK_GROUP",
                {"name": payload.get("name", ""), "parent": sg_parent})
            if tally_queued: db.commit()

        elif entity_type == "unit":
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_UNIT",
                {"name": payload.get("name", ""), "symbol": payload.get("symbol", ""),
                 "decimal_places": str(payload.get("decimal_places", "0"))})
            if tally_queued: db.commit()

        elif entity_type == "godown":
            gd_parent = (payload.get("parent") or "").strip()
            # Strip implicit root names — not addressable in all TallyPrime editions
            if gd_parent.lower() in ("main location", "primary", ""):
                gd_parent = ""
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_GODOWN",
                {"name": payload.get("name", ""), "parent": gd_parent})
            if tally_queued: db.commit()

        elif entity_type == "receipt":
            date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try: d = datetime.fromisoformat(date_str)
            except Exception: d = datetime.now(timezone.utc)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_RECEIPT_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "account_ledger": payload.get("account_ledger", "Cash"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Receipt")})
            if tally_queued: db.commit()

        elif entity_type == "payment":
            date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try: d = datetime.fromisoformat(date_str)
            except Exception: d = datetime.now(timezone.utc)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_PAYMENT_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "account_ledger": payload.get("account_ledger", "Cash"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Payment")})
            if tally_queued: db.commit()

        elif entity_type == "journal":
            date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try: d = datetime.fromisoformat(date_str)
            except Exception: d = datetime.now(timezone.utc)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_JOURNAL_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "dr_ledger": payload.get("dr_ledger", ""),
                 "cr_ledger": payload.get("cr_ledger", ""),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Journal Entry")})
            if tally_queued: db.commit()

        elif entity_type == "credit_note":
            date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try: d = datetime.fromisoformat(date_str)
            except Exception: d = datetime.now(timezone.utc)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_CREDIT_NOTE",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "sales_ledger": payload.get("sales_ledger", "Sales"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Sales Return")})
            if tally_queued: db.commit()

        elif entity_type == "debit_note":
            date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try: d = datetime.fromisoformat(date_str)
            except Exception: d = datetime.now(timezone.utc)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_DEBIT_NOTE",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "purchase_ledger": payload.get("purchase_ledger", "Purchases"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Purchase Return")})
            if tally_queued: db.commit()

        elif entity_type == "contra":
            date_str = payload.get("date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try: d = datetime.fromisoformat(date_str)
            except Exception: d = datetime.now(timezone.utc)
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_CONTRA_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "from_account": payload.get("from_account", "Cash"),
                 "to_account": payload.get("to_account", "Bank"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Fund Transfer")})
            if tally_queued: db.commit()

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
