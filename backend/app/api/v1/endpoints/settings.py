from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.models.user import User
from app.models.company import Company
from app.schemas.company import CompanyUpdate
from app.core.config import settings
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
from pydantic import BaseModel
from typing import Optional, Literal
import uuid

VALID_PROVIDERS = {"demo", "groq", "openrouter", "ollama"}

router = APIRouter(prefix="/settings", tags=["settings"])


class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None


class AISettingsUpdate(BaseModel):
    provider: str


@router.get("/company")
def get_company_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    return {
        "id": str(company.id), "name": company.name, "legal_name": company.legal_name,
        "gst_number": company.gst_number, "pan_number": company.pan_number,
        "address": company.address, "city": company.city, "state": company.state,
        "country": company.country, "pincode": company.pincode,
        "phone": company.phone, "email": company.email, "website": company.website,
        "currency": company.currency, "fiscal_year_start": company.fiscal_year_start,
    }


@router.put("/company")
def update_company_settings(
    data: CompanyUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.SETTINGS_CHANGE,
                      entity_type="company", description="Company settings updated")
    return {"message": "Company settings updated"}


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id), "full_name": current_user.full_name,
        "email": current_user.email, "role": current_user.role.value,
        "is_active": current_user.is_active,
        "last_login": current_user.last_login.isoformat() if current_user.last_login else None,
    }


@router.put("/profile")
def update_profile(
    data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if data.full_name:
        current_user.full_name = data.full_name
    if data.email:
        existing = db.query(User).filter(User.email == data.email, User.id != current_user.id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        current_user.email = data.email
    db.commit()
    return {"message": "Profile updated"}


@router.get("/ai")
def get_ai_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    # Company's stored choice overrides the env-var default
    active_provider = (company.ai_provider if company and company.ai_provider else None) or settings.AI_PROVIDER

    def _is_demo(p: str) -> bool:
        if p == "demo":
            return True
        if p == "openrouter" and not settings.OPENROUTER_API_KEY:
            return True
        if p == "groq" and not settings.GROQ_API_KEY:
            return True
        return False

    return {
        "provider": active_provider,
        "is_demo_mode": _is_demo(active_provider),
        "available_providers": [
            {
                "id": "demo",
                "name": "Demo Mode",
                "description": "Built-in rule-based responses — no API key needed",
                "configured": True,
            },
            {
                "id": "groq",
                "name": "Groq",
                "description": "Fast inference — llama-3.3-70b-versatile",
                "configured": bool(settings.GROQ_API_KEY),
            },
            {
                "id": "openrouter",
                "name": "OpenRouter",
                "description": "Free models — gemma-4-26b-a4b-it",
                "configured": bool(settings.OPENROUTER_API_KEY),
            },
            {
                "id": "ollama",
                "name": "Ollama (Local)",
                "description": "Fully private — runs on your machine",
                "configured": bool(settings.OLLAMA_BASE_URL),
            },
        ],
    }


@router.put("/ai")
def update_ai_settings(
    data: AISettingsUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if data.provider not in VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Invalid provider. Must be one of: {', '.join(VALID_PROVIDERS)}")
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    company.ai_provider = data.provider
    db.commit()
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.SETTINGS_CHANGE,
                      entity_type="ai", description=f"AI provider changed to {data.provider}")
    return {"message": "AI provider updated", "provider": data.provider}


@router.get("/users")
def list_users(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    users = db.query(User).filter(User.company_id == current_user.company_id).all()
    return [
        {
            "id": str(u.id), "full_name": u.full_name, "email": u.email,
            "role": u.role.value, "is_active": u.is_active,
            "last_login": u.last_login.isoformat() if u.last_login else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]
