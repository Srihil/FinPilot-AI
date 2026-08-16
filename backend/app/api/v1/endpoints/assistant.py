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
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_RECEIPT_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "account_ledger": payload.get("account_ledger", "Cash"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Receipt")})
            if tally_queued: db.commit()

        elif entity_type == "payment":
            d = _parse_date(payload.get("date", ""))
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_PAYMENT_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "account_ledger": payload.get("account_ledger", "Cash"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Payment")})
            if tally_queued: db.commit()

        elif entity_type == "journal":
            d = _parse_date(payload.get("date", ""))
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_JOURNAL_VOUCHER",
                {"date": d.strftime("%Y%m%d"), "dr_ledger": payload.get("dr_ledger", ""),
                 "cr_ledger": payload.get("cr_ledger", ""),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Journal Entry")})
            if tally_queued: db.commit()

        elif entity_type == "credit_note":
            d = _parse_date(payload.get("date", ""))
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_CREDIT_NOTE",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "sales_ledger": payload.get("sales_ledger", "Sales"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Sales Return")})
            if tally_queued: db.commit()

        elif entity_type == "debit_note":
            d = _parse_date(payload.get("date", ""))
            tally_queued = queue_tally_write(db, current_user.company_id, "CREATE_DEBIT_NOTE",
                {"date": d.strftime("%Y%m%d"), "party_ledger": payload.get("party_ledger", ""),
                 "purchase_ledger": payload.get("purchase_ledger", "Purchases"),
                 "amount": str(int(float(payload.get("amount", 0)))),
                 "narration": payload.get("narration", "Purchase Return")})
            if tally_queued: db.commit()

        elif entity_type == "contra":
            d = _parse_date(payload.get("date", ""))
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
