import pytest
from tests.conftest import get_auth_token, auth_headers


def test_signup(client):
    resp = client.post("/api/auth/signup", json={
        "full_name": "Test User",
        "email": "newuser@test.com",
        "password": "Password@123",
        "confirm_password": "Password@123",
        "company_name": "Test Company",
        "accept_terms": True,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "newuser@test.com"
    assert data["user"]["role"] == "ADMIN"


def test_signup_duplicate_email(client, admin_user):
    resp = client.post("/api/auth/signup", json={
        "full_name": "Duplicate",
        "email": admin_user.email,
        "password": "Password@123",
        "confirm_password": "Password@123",
        "company_name": "Another Company",
        "accept_terms": True,
    })
    assert resp.status_code == 400


def test_login_success(client, admin_user):
    resp = client.post("/api/auth/login", json={
        "email": admin_user.email,
        "password": "Password@123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client, admin_user):
    resp = client.post("/api/auth/login", json={
        "email": admin_user.email,
        "password": "WrongPassword",
    })
    assert resp.status_code == 401


def test_get_me(client, admin_user):
    token = get_auth_token(client, admin_user.email, "Password@123")
    resp = client.get("/api/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == admin_user.email


def test_unauthorized_without_token(client):
    resp = client.get("/api/dashboard/overview")
    assert resp.status_code == 403  # FastAPI returns 403 for missing bearer


def test_invalid_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid_token"})
    assert resp.status_code == 401
