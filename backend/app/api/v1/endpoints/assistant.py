from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.company import Company
from app.models.ai_conversation import AIConversation, AIMessage, MessageRole
from app.agents.finance_agent import FinanceAgent
from app.agents.transaction_agent import TransactionAgent
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from pydantic import BaseModel
from typing import Optional
import uuid

router = APIRouter(prefix="/assistant", tags=["assistant"])


class ConversationCreate(BaseModel):
    title: Optional[str] = "New Conversation"


class ConversationRename(BaseModel):
    title: str


class MessageCreate(BaseModel):
    content: str


class TransactionProposal(BaseModel):
    text: str


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

    # Run finance agent
    agent = FinanceAgent(db)
    result = agent.chat(data.content, str(current_user.company_id), history_for_agent, provider_override)

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
