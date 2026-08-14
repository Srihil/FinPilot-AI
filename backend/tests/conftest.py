import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from app.main import app
from app.db.base import Base, get_db
from app.models.company import Company
from app.models.user import User, UserRole
from app.core.security import hash_password

# Use PostgreSQL for testing to avoid SQLite compatibility issues with UUID/JSONB
# Falls back to SQLite if DATABASE_URL not set (limited tests)
import os
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://finpilot:finpilot_password@localhost:5432/finpilot_test"
)

engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def create_tables():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    db = TestingSessionLocal()
    yield db
    db.rollback()
    db.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def company_a(db):
    company = Company(name="Company A Test", currency="INR", fiscal_year_start="04-01")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@pytest.fixture
def company_b(db):
    company = Company(name="Company B Test", currency="INR", fiscal_year_start="04-01")
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@pytest.fixture
def admin_user(db, company_a):
    import uuid
    email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    user = User(
        company_id=company_a.id, full_name="Admin User",
        email=email, hashed_password=hash_password("Password@123"),
        role=UserRole.ADMIN, is_active=True, is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def accountant_user(db, company_a):
    import uuid
    email = f"accountant_{uuid.uuid4().hex[:8]}@test.com"
    user = User(
        company_id=company_a.id, full_name="Accountant User",
        email=email, hashed_password=hash_password("Password@123"),
        role=UserRole.ACCOUNTANT, is_active=True, is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def viewer_user(db, company_a):
    import uuid
    email = f"viewer_{uuid.uuid4().hex[:8]}@test.com"
    user = User(
        company_id=company_a.id, full_name="Viewer User",
        email=email, hashed_password=hash_password("Password@123"),
        role=UserRole.VIEWER, is_active=True, is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def company_b_admin(db, company_b):
    import uuid
    email = f"b_admin_{uuid.uuid4().hex[:8]}@test.com"
    user = User(
        company_id=company_b.id, full_name="Company B Admin",
        email=email, hashed_password=hash_password("Password@123"),
        role=UserRole.ADMIN, is_active=True, is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_auth_token(client, email: str, password: str) -> str:
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, f"Login failed for {email}: {resp.json()}"
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
