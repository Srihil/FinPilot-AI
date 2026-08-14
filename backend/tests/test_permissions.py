"""
Authorization tests: Enforce role-based permissions.
VIEWER cannot modify data. Only ADMIN can approve.
"""
import pytest
from tests.conftest import get_auth_token, auth_headers


def test_viewer_cannot_create_customer(client, viewer_user):
    token = get_auth_token(client, viewer_user.email, "Password@123")
    resp = client.post("/api/customers", headers=auth_headers(token), json={
        "name": "New Customer", "country": "India",
        "payment_terms_days": 30, "credit_limit": 0,
    })
    assert resp.status_code == 403


def test_viewer_cannot_create_vendor(client, viewer_user):
    token = get_auth_token(client, viewer_user.email, "Password@123")
    resp = client.post("/api/vendors", headers=auth_headers(token), json={
        "name": "New Vendor", "country": "India", "payment_terms_days": 30,
    })
    assert resp.status_code == 403


def test_viewer_can_view_dashboard(client, viewer_user):
    token = get_auth_token(client, viewer_user.email, "Password@123")
    resp = client.get("/api/dashboard/overview", headers=auth_headers(token))
    assert resp.status_code == 200


def test_accountant_can_create_customer(client, accountant_user):
    token = get_auth_token(client, accountant_user.email, "Password@123")
    resp = client.post("/api/customers", headers=auth_headers(token), json={
        "name": "Accountant Created Customer", "country": "India",
        "payment_terms_days": 30, "credit_limit": 0,
    })
    assert resp.status_code == 200


def test_accountant_cannot_approve_invoice(client, accountant_user, admin_user, db):
    # Create a test invoice first via admin
    admin_token = get_auth_token(client, admin_user.email, "Password@123")
    accountant_token = get_auth_token(client, accountant_user.email, "Password@123")

    # Accountant tries to approve a non-existent approval
    import uuid
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/approvals/{fake_id}/approve",
                       headers=auth_headers(accountant_token), json={})
    assert resp.status_code == 403, "Accountant should not be able to approve"


def test_admin_can_approve(client, admin_user, db):
    token = get_auth_token(client, admin_user.email, "Password@123")
    # Verify admin can access approval endpoints (even if 404 for missing record)
    import uuid
    fake_id = str(uuid.uuid4())
    resp = client.post(f"/api/approvals/{fake_id}/approve",
                       headers=auth_headers(token), json={})
    # Should get 404 (not found) not 403 (forbidden)
    assert resp.status_code == 404
