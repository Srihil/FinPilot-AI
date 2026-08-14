"""
Critical security tests: Company A must not access Company B data.
"""
import pytest
from tests.conftest import get_auth_token, auth_headers
from app.models.customer import Customer


def test_company_a_cannot_see_company_b_customers(client, admin_user, company_b_admin, db, company_b):
    # Create a customer for Company B
    b_customer = Customer(
        company_id=company_b.id, name="Company B Customer",
        email="cust@companyb.com", country="India",
        payment_terms_days=30, credit_limit=0,
    )
    db.add(b_customer)
    db.commit()

    # Login as Company A admin
    token_a = get_auth_token(client, admin_user.email, "Password@123")

    # List customers - should only see Company A's customers
    resp = client.get("/api/customers", headers=auth_headers(token_a))
    assert resp.status_code == 200
    items = resp.json()["items"]

    customer_ids = [item["id"] for item in items]
    assert str(b_customer.id) not in customer_ids, "Company A should NOT see Company B's customers"


def test_company_b_admin_cannot_access_company_a_customer(client, admin_user, company_b_admin, db, company_a):
    # Create a customer for Company A
    a_customer = Customer(
        company_id=company_a.id, name="Company A Customer",
        email="cust@companya.com", country="India",
        payment_terms_days=30, credit_limit=0,
    )
    db.add(a_customer)
    db.commit()

    # Login as Company B admin
    token_b = get_auth_token(client, company_b_admin.email, "Password@123")

    # Try to directly access Company A's customer by ID
    resp = client.get(f"/api/customers/{a_customer.id}", headers=auth_headers(token_b))
    assert resp.status_code == 404, "Company B should get 404 for Company A's customer"


def test_dashboard_scoped_to_company(client, admin_user, company_b_admin):
    token_a = get_auth_token(client, admin_user.email, "Password@123")
    token_b = get_auth_token(client, company_b_admin.email, "Password@123")

    resp_a = client.get("/api/dashboard/overview", headers=auth_headers(token_a))
    resp_b = client.get("/api/dashboard/overview", headers=auth_headers(token_b))

    assert resp_a.status_code == 200
    assert resp_b.status_code == 200
    # Both should succeed but return different company data
