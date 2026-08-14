from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.user import User, UserRole
from app.models.company import Company
from app.core.security import hash_password, verify_password, create_access_token
from app.schemas.auth import SignupRequest, LoginRequest
from datetime import datetime, timezone
import uuid


class AuthService:
    def signup(self, db: Session, data: SignupRequest) -> dict:
        existing = db.query(User).filter(User.email == data.email).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        company = Company(name=data.company_name)
        db.add(company)
        db.flush()

        user = User(
            company_id=company.id,
            full_name=data.full_name,
            email=data.email,
            hashed_password=hash_password(data.password),
            role=UserRole.ADMIN,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        token = create_access_token({"sub": str(user.id), "company_id": str(company.id), "role": user.role.value})
        return {"user": user, "token": token}

    def login(self, db: Session, data: LoginRequest) -> dict:
        user = db.query(User).filter(User.email == data.email, User.is_active == True).first()
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user.last_login = datetime.now(timezone.utc)
        db.commit()

        token = create_access_token({"sub": str(user.id), "company_id": str(user.company_id), "role": user.role.value})
        return {"user": user, "token": token}

    def change_password(self, db: Session, user: User, current_password: str, new_password: str) -> None:
        if not verify_password(current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        user.hashed_password = hash_password(new_password)
        db.commit()


auth_service = AuthService()
