# -*- coding: utf-8 -*-
"""
Full create-then-delete test for every entity type in FinPilot.

Creates TEST entries via the AI Create API, then immediately deletes them.
Does NOT touch TallyPrime data (entries stay in 'pending' state = local delete only).

Run: python -X utf8 backend/tests/test_delete_flow.py
"""
import sys, io, time, json
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = "http://localhost:8000"
EMAIL = "sahil@gmail.com"
PASSWORD = "sahil2709"
RS = chr(0x20B9)  # ₹

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api(method, path, body=None, token=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read()).get("detail", str(e))
        except Exception:
            detail = str(e)
        return e.code, {"error": detail}

def login():
    status, body = api("POST", "/api/auth/login",
                       {"email": EMAIL, "password": PASSWORD})
    if status != 200 or "access_token" not in body:
        print(f"  LOGIN FAILED ({status}): {body}")
        sys.exit(1)
    return body["access_token"]

def ai_create(token, text):
    """Extract entity then create it. Returns (entity_type, entity_id)."""
    s, ext = api("POST", "/api/assistant/extract-entity", {"text": text}, token)
    if s != 200:
        return None, None, f"extract failed {s}: {ext}"
    entity_type = ext.get("entity_type", "")
    data = ext.get("data", {})
    s2, created = api("POST", "/api/assistant/create-entity",
                      {"entity_type": entity_type, "data": data}, token)
    if s2 not in (200, 201):
        return entity_type, None, f"create failed {s2}: {created}"
    return entity_type, created.get("id"), None

# ---------------------------------------------------------------------------
# Delete routing — maps entity_type to the right DELETE endpoint
# ---------------------------------------------------------------------------

def delete_entity(token, entity_type, entity_id):
    voucher_expense_types = {
        "receipt", "payment", "journal", "credit_note", "debit_note",
        "contra", "custom_voucher", "expense",
    }
    voucher_invoice_types = {"invoice", "sales_invoice", "purchase_bill"}
    stock_txn_types = {
        "stock_journal", "physical_stock", "delivery_note",
        "receipt_note", "rejection_in", "rejection_out",
    }

    if entity_type in voucher_invoice_types:
        path = f"/api/management/vouchers/invoice/{entity_id}"
    elif entity_type in voucher_expense_types:
        path = f"/api/management/vouchers/expense/{entity_id}"
    elif entity_type in stock_txn_types:
        path = f"/api/inventory/stock-transactions/{entity_id}"
    elif entity_type == "ledger":
        path = f"/api/management/ledgers/{entity_id}"
    elif entity_type == "group":
        path = f"/api/management/groups/{entity_id}"
    elif entity_type == "unit":
        path = f"/api/management/units/{entity_id}"
    elif entity_type == "godown":
        path = f"/api/management/godowns/{entity_id}"
    elif entity_type == "stock_item":
        path = f"/api/management/stock-items/{entity_id}"
    elif entity_type == "stock_group":
        path = f"/api/management/stock-groups/{entity_id}"
    elif entity_type == "customer":
        path = f"/api/customers/{entity_id}"
    elif entity_type == "vendor":
        path = f"/api/vendors/{entity_id}"
    elif entity_type == "product":
        path = f"/api/products/{entity_id}"
    else:
        return False, f"unknown entity_type '{entity_type}'"

    status, body = api("DELETE", path, token=token)
    if status in (200, 204):
        msg = body.get("message") or body.get("status") or "deleted" if isinstance(body, dict) else "deleted"
        return True, msg
    return False, f"HTTP {status}: {body}"

# ---------------------------------------------------------------------------
# Test cases: (label, prompt_text)
# ---------------------------------------------------------------------------

TESTS = [
    # ── ACCOUNTING VOUCHERS ──────────────────────────────────────────────
    ("Sales Invoice",
     f"Sales invoice for Kumar Enterprises {RS}1000 on 1 Sept 2026"),
    ("Purchase Bill",
     f"Purchase bill from Kapoor Suppliers {RS}1000 on 1 Sept 2026"),
    ("Receipt",
     f"Receipt from Kumar Enterprises {RS}1000 in Cash on 1 Sept 2026"),
    ("Payment",
     f"Payment to Kapoor Suppliers {RS}1000 from Cash on 1 Sept 2026"),
    ("Journal",
     f"Journal entry debit Salary Payable credit Cash {RS}1000 on 1 Sept 2026"),
    ("Credit Note",
     f"Credit note for Kumar Enterprises {RS}500 on 1 Sept 2026"),
    ("Debit Note",
     f"Debit note for Kapoor Suppliers {RS}500 on 1 Sept 2026"),
    ("Contra",
     f"Contra transfer {RS}1000 from Cash to HDFC Bank on 1 Sept 2026"),
    # ── CUSTOM VOUCHERS ──────────────────────────────────────────────────
    ("Custom - GST Bill",
     f"Create a GST Bill for Kumar Enterprises {RS}1000 on 1 Sept 2026"),
    ("Custom - Petty Cash",
     f"Create a Petty Cash entry {RS}200 on 1 Sept 2026"),
    # ── STOCK TRANSACTIONS ───────────────────────────────────────────────
    ("Stock Journal",
     "Transfer 1 Remote from Main Location to Chennai on 1 Sept 2026"),
    ("Physical Stock",
     "Physical stock count 1 Remote at Main Location on 1 Sept 2026"),
    ("Delivery Note",
     "Delivery Note for Kumar Enterprises 1 Remote from Main Location on 1 Sept 2026"),
    ("Receipt Note",
     "Receipt Note from Kapoor Suppliers 1 Remote at Main Location on 1 Sept 2026"),
    ("Rejection In",
     "Rejection In from Kumar Enterprises 1 Remote at Main Location on 1 Sept 2026"),
    ("Rejection Out",
     "Rejection Out to Kapoor Suppliers 1 Remote from Main Location on 1 Sept 2026"),
    # ── MASTER ENTITIES ──────────────────────────────────────────────────
    ("Godown",
     "Add Godown TEST_DEL_Godown_X1 under Main Location"),
    ("Unit",
     "Add unit TEST_DEL_Unit_X1 symbol TDUX"),
    ("Stock Group",
     "Add stock group TEST_DEL_StockGroup_X1 under Primary"),
    ("Stock Item",
     f"Add stock item TEST_DEL_Item_X1 unit Nos rate 100"),
    ("Account Group",
     "Add group TEST_DEL_AccGroup_X1 under Indirect Expenses"),
    ("Ledger",
     "Add ledger TEST_DEL_Ledger_X1 under Sundry Debtors"),
    ("Customer",
     "Add customer TEST_DEL_Customer_X1 phone 9999999999"),
    ("Vendor",
     "Add vendor TEST_DEL_Vendor_X1 phone 9999999999"),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    print(f"\n  Logging in as {EMAIL}...")
    token = login()
    print(f"  Logged in. Running {len(TESTS)} create+delete tests.\n")
    print(f"  NOTE: Entries are deleted immediately (pending state = local-only delete,")
    print(f"        no TallyPrime data modified).\n")

    passed = failed = 0
    failures = []

    for label, prompt in TESTS:
        # Step 1: Create
        entity_type, entity_id, err = ai_create(token, prompt)

        if err or not entity_id:
            status = "FAIL"
            reason = f"CREATE failed — {err}"
            failed += 1
            failures.append((label, reason))
            print(f"  FAIL  [{label:30s}]  {reason}")
            continue

        # Step 2: Delete immediately (while still pending → local delete only)
        ok, msg = delete_entity(token, entity_type, entity_id)

        if ok:
            passed += 1
            print(f"  PASS  [{label:30s}]  type={entity_type}  del: {str(msg)[:60]}")
        else:
            failed += 1
            reason = f"DELETE failed — {msg}"
            failures.append((label, reason))
            print(f"  FAIL  [{label:30s}]  type={entity_type}  {reason}")

    print(f"\n{'=' * 64}")
    print(f"  RESULT: {passed} PASSED   {failed} FAILED   out of {passed + failed}")
    print(f"{'=' * 64}")

    if failures:
        print("\n  Failures:")
        for label, reason in failures:
            print(f"    - {label}: {reason}")

    return failed == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
