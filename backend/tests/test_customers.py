import pytest
from tests.conftest import get_auth_token, auth_headers


def test_create_customer(client, admin_user):
    token = get_auth_token(client, admin_user.email, "Password@123")
    resp = client.post("/api/customers", headers=auth_headers(token), json={
        "name": "Test Customer Ltd.", "email": "test@customer.com",
        "phone": "+91 22 1234 5678", "country": "India",
        "gst_number": "27AABCT1234A1ZV", "payment_terms_days": 30, "credit_limit": 500000,
    })
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Customer Ltd."


def test_list_customers(client, admin_user):
    token = get_auth_token(client, admin_user.email, "Password@123")
    resp = client.get("/api/customers", headers=auth_headers(token))
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


def test_customer_search(client, admin_user):
    token = get_auth_token(client, admin_user.email, "Password@123")
    # Search by name
    resp = client.get("/api/customers?search=Test+Customer", headers=auth_headers(token))
    assert resp.status_code == 200


def test_update_customer(client, admin_user):
    token = get_auth_token(client, admin_user.email, "Password@123")

    # Create
    create_resp = client.post("/api/customers", headers=auth_headers(token), json={
        "name": "Update Test Customer", "country": "India",
        "payment_terms_days": 30, "credit_limit": 0,
    })
    customer_id = create_resp.json()["id"]

    # Update
    resp = client.put(f"/api/customers/{customer_id}", headers=auth_headers(token), json={
        "name": "Updated Customer Name", "payment_terms_days": 45,
    })
    assert resp.status_code == 200
    assert "Updated" in resp.json()["name"]
