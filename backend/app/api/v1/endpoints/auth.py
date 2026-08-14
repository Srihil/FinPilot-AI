from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.schemas.auth import SignupRequest, LoginRequest, TokenResponse, UserResponse, ChangePasswordRequest
from app.services.auth_service import auth_service
from app.auth.dependencies import get_current_user
from app.models.user import User
from app.models.audit_log import AuditAction
from app.services.audit_service import audit_service
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse)
def signup(data: SignupRequest, db: Session = Depends(get_db)):
    result = auth_service.signup(db, data)
    user = result["user"]
    audit_service.log(db, user.company_id, user.id, AuditAction.CREATE,
                      entity_type="user", description=f"User {user.email} signed up")
    return {
        "access_token": result["token"],
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "company_id": str(user.company_id),
            "is_active": user.is_active,
        }
    }


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    result = auth_service.login(db, data)
    user = result["user"]
    ip = request.client.host if request.client else None
    audit_service.log(db, user.company_id, user.id, AuditAction.LOGIN,
                      description=f"User {user.email} logged in", ip_address=ip)
    return {
        "access_token": result["token"],
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role.value,
            "company_id": str(user.company_id),
            "is_active": user.is_active,
        }
    }


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "role": current_user.role.value,
        "company_id": str(current_user.company_id),
        "is_active": current_user.is_active,
    }


@router.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(db, current_user, data.current_password, data.new_password)
    audit_service.log(db, current_user.company_id, current_user.id, AuditAction.PASSWORD_CHANGE,
                      description="Password changed")
    return {"message": "Password updated successfully"}
