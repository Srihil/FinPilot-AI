# -*- coding: utf-8 -*-
"""
Delete flow integration tests for every entity type in FinPilot.

TWO test suites:

  Suite A — Pending-state delete (local-only)
    Creates entries via AI Create, then immediately deletes while still
    in "pending" state (connector hasn't confirmed the create in TallyPrime yet).
    No TallyPrime data is modified.

    Vouchers (invoice/expense):  expect HTTP 200, {"status": "deleted", "tally_confirmed": False}
    Stock transactions:          expect HTTP 200, {"deleted": True}
    Master entities:             expect HTTP 200, {"status": "deleted", ...}  or  204

  Suite B — Synced-state delete (Tally-confirmed-first)
    Marks an entry as "synced" via the debug endpoint, then deletes.
    If connector active:   HTTP 200, {"status": "pending"}  (queued for Tally DELETE)
    If connector missing:  HTTP 409  (record protected, user told to connect Tally)

Run: python -X utf8 backend/tests/test_delete_flow.py
"""
import sys, io, json, time
import urllib.request, urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE     = "http://localhost:8000"
EMAIL    = "sahil@gmail.com"
PASSWORD = "sahil2709"
RS       = chr(0x20B9)  # ₹
TS       = str(int(time.time()))[-5:]   # 5-digit suffix so test names are unique per run

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
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, {}
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


def delete_path(entity_type, entity_id):
    voucher_expense = {
        "receipt", "payment", "journal", "credit_note", "debit_note",
        "contra", "custom_voucher", "expense",
    }
    voucher_invoice = {"invoice", "sales_invoice", "purchase_bill"}
    stock_txn = {
        "stock_journal", "physical_stock", "delivery_note",
        "receipt_note", "rejection_in", "rejection_out",
    }
    if entity_type in voucher_invoice:
        return f"/api/management/vouchers/invoice/{entity_id}", "voucher"
    if entity_type in voucher_expense:
        return f"/api/management/vouchers/expense/{entity_id}", "voucher"
    if entity_type in stock_txn:
        return f"/api/inventory/stock-transactions/{entity_id}", "stock_txn"
    paths = {
        "ledger":       (f"/api/management/ledgers/{entity_id}",      "master"),
        "group":        (f"/api/management/groups/{entity_id}",       "master"),
        "unit":         (f"/api/management/units/{entity_id}",        "master"),
        "godown":       (f"/api/management/godowns/{entity_id}",      "master"),
        "stock_item":   (f"/api/management/stock-items/{entity_id}",  "master"),
        "stock_group":  (f"/api/management/stock-groups/{entity_id}", "master"),
        "customer":     (f"/api/customers/{entity_id}",               "other"),
        "vendor":       (f"/api/vendors/{entity_id}",                 "other"),
        "product":      (f"/api/products/{entity_id}",                "other"),
    }
    p = paths.get(entity_type)
    return p if p else (None, None)


def check_delete_response(entity_kind, status, body):
    """
    Returns (ok, detail_msg).

    entity_kind:
      "voucher"   — expect status=deleted + tally_confirmed=False
      "stock_txn" — expect HTTP 200 with deleted=True in body
      "master"    — expect HTTP 200/204 with status=deleted (may lack tally_confirmed)
      "other"     — expect HTTP 200/204, any success body
    """
    if status not in (200, 204):
        return False, f"HTTP {status}: {body.get('error', body)}"

    if entity_kind == "voucher":
        resp_status = body.get("status", "")
        tally_conf  = body.get("tally_confirmed", True)
        if resp_status == "deleted" and tally_conf is False:
            return True, f"status=deleted  tally_confirmed=False"
        return False, f"wrong response: status={resp_status!r} tally_confirmed={tally_conf!r}"

    if entity_kind == "stock_txn":
        if body.get("deleted") is True:
            return True, "deleted=True"
        return False, f"wrong response: {body}"

    if entity_kind == "master":
        resp_status = body.get("status", "")
        if resp_status == "deleted" or status == 204:
            return True, f"status={resp_status or 'ok'}"
        return False, f"wrong response: {body}"

    # "other" — just check HTTP success
    return True, f"HTTP {status}"


# ---------------------------------------------------------------------------
# Suite A test cases
# ---------------------------------------------------------------------------

SUITE_A_TESTS = [
    # ── ACCOUNTING VOUCHERS ──────────────────────────────────────────────
    ("Sales Invoice",   f"Sales invoice for Kumar Enterprises {RS}1000 on 1 Sept 2026"),
    ("Purchase Bill",   f"Purchase bill from Kapoor Suppliers {RS}1000 on 1 Sept 2026"),
    ("Receipt",         f"Receipt from Kumar Enterprises {RS}1000 in Cash on 1 Sept 2026"),
    ("Payment",         f"Payment to Kapoor Suppliers {RS}1000 from Cash on 1 Sept 2026"),
    ("Journal",         f"Journal entry debit Salary Payable credit Cash {RS}1000 on 1 Sept 2026"),
    ("Credit Note",     f"Credit note for Kumar Enterprises {RS}500 on 1 Sept 2026"),
    ("Debit Note",      f"Debit note for Kapoor Suppliers {RS}500 on 1 Sept 2026"),
    ("Contra",          f"Contra transfer {RS}1000 from Cash to HDFC Bank on 1 Sept 2026"),
    ("Custom GST Bill", f"Create a GST Bill for Kumar Enterprises {RS}1000 on 1 Sept 2026"),
    ("Custom Petty Cash", f"Create a Petty Cash entry {RS}200 on 1 Sept 2026"),
    # ── STOCK TRANSACTIONS ───────────────────────────────────────────────
    ("Stock Journal",   "Transfer 1 Remote from Main Location to Chennai on 1 Sept 2026"),
    ("Physical Stock",  "Physical stock count 1 Remote at Main Location on 1 Sept 2026"),
    ("Delivery Note",   "Delivery Note for Kumar Enterprises 1 Remote from Main Location on 1 Sept 2026"),
    ("Receipt Note",    "Receipt Note from Kapoor Suppliers 1 Remote at Main Location on 1 Sept 2026"),
    ("Rejection In",    "Rejection In from Kumar Enterprises 1 Remote at Main Location on 1 Sept 2026"),
    ("Rejection Out",   "Rejection Out to Kapoor Suppliers 1 Remote from Main Location on 1 Sept 2026"),
    # ── MASTER ENTITIES (unique names per run via TS suffix) ─────────────
    ("Godown",      f"Add Godown TD_Godown_{TS} under Main Location"),
    ("Unit",        f"Add unit TD_Unit_{TS} symbol TDU{TS}"),
    ("Stock Group", f"Add stock group TD_SG_{TS} under Primary"),
    ("Stock Item",  f"Add stock item TD_Item_{TS} unit Nos rate 100"),
    ("Acct Group",  f"Add group TD_AG_{TS} under Indirect Expenses"),
    ("Ledger",      f"Add ledger TD_Ledger_{TS} under Sundry Debtors"),
    ("Customer",    f"Add customer TD_Cust_{TS} phone 9999999999"),
    ("Vendor",      f"Add vendor TD_Vend_{TS} phone 9999999999"),
]

# ---------------------------------------------------------------------------
# Suite B test cases
# ---------------------------------------------------------------------------

SUITE_B_VOUCHERS = [
    ("Sales Invoice [synced]",  f"Sales invoice for Kumar Enterprises {RS}500 on 2 Sept 2026",  "invoice"),
    ("Purchase Bill [synced]",  f"Purchase bill from Kapoor Suppliers {RS}500 on 2 Sept 2026",  "expense"),
    ("Payment [synced]",        f"Payment to Kapoor Suppliers {RS}500 from Cash on 2 Sept 2026","expense"),
    ("Receipt [synced]",        f"Receipt from Kumar Enterprises {RS}500 in Cash on 2 Sept 2026","expense"),
]


def mark_as_synced(token, entity_type, entity_id):
    path = "/api/management/debug/mark-synced"
    status, _ = api("POST", path, {"entity_type": entity_type, "entity_id": entity_id}, token)
    return status in (200, 201, 204)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_suite_a(token):
    print("\n" + "=" * 64)
    print("  SUITE A — Pending-state delete (local-only, no TallyPrime)")
    print("=" * 64)

    passed = failed = 0
    failures = []

    for label, prompt in SUITE_A_TESTS:
        entity_type, entity_id, err = ai_create(token, prompt)
        if err or not entity_id:
            failed += 1
            reason = f"CREATE failed — {err}"
            failures.append((label, reason))
            print(f"  FAIL  [{label:30s}]  {reason}")
            continue

        path, kind = delete_path(entity_type, entity_id)
        if path is None:
            failed += 1
            reason = f"unknown entity_type '{entity_type}'"
            failures.append((label, reason))
            print(f"  FAIL  [{label:30s}]  {reason}")
            continue

        status, body = api("DELETE", path, token=token)
        ok, detail = check_delete_response(kind, status, body)
        if ok:
            passed += 1
            print(f"  PASS  [{label:30s}]  {detail}")
        else:
            failed += 1
            failures.append((label, detail))
            print(f"  FAIL  [{label:30s}]  {detail}")

    return passed, failed, failures


def run_suite_b(token):
    print("\n" + "=" * 64)
    print("  SUITE B — Synced-state delete (Tally-confirmed-first)")
    print("  Expected: status=pending (connector active)  OR  HTTP 409 (no connector)")
    print("=" * 64)

    passed = failed = 0
    failures = []

    for label, prompt, expected_entity in SUITE_B_VOUCHERS:
        entity_type, entity_id, err = ai_create(token, prompt)
        if err or not entity_id:
            failed += 1
            reason = f"CREATE failed — {err}"
            failures.append((label, reason))
            print(f"  FAIL  [{label:30s}]  {reason}")
            continue

        synced = mark_as_synced(token, expected_entity, entity_id)
        if not synced:
            print(f"  SKIP  [{label:30s}]  mark-synced endpoint unavailable")
            continue

        path, kind = delete_path(entity_type, entity_id)
        status, body = api("DELETE", path, token=token)

        if status == 200 and body.get("status") == "pending":
            passed += 1
            print(f"  PASS  [{label:30s}]  status=pending (connector active, queued for Tally DELETE)")
        elif status == 409:
            passed += 1
            print(f"  PASS  [{label:30s}]  HTTP 409 (no connector — record protected, not deleted)")
        else:
            failed += 1
            reason = f"HTTP {status}: {body}"
            failures.append((label, reason))
            print(f"  FAIL  [{label:30s}]  {reason}")

    return passed, failed, failures


def main():
    print(f"\n  Logging in as {EMAIL}...")
    token = login()
    print(f"  OK  (run suffix: {TS})")

    tp = tf = 0
    all_fail = []

    a_p, a_f, a_fail = run_suite_a(token)
    tp += a_p; tf += a_f; all_fail.extend(a_fail)

    b_p, b_f, b_fail = run_suite_b(token)
    tp += b_p; tf += b_f; all_fail.extend(b_fail)

    print(f"\n{'=' * 64}")
    print(f"  RESULT: {tp} PASSED   {tf} FAILED   out of {tp + tf}")
    print(f"{'=' * 64}")

    if all_fail:
        print("\n  Failures:")
        for label, reason in all_fail:
            print(f"    - {label}: {reason}")

    return tf == 0


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
