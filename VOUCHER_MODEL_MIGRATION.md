# Voucher Model Migration + Voucher CRUD UI — Implementation Brief

> Hand this entire file to a future Claude session as the task prompt.
> Read every section before writing a single line of code.

---

## CONTEXT — WHO YOU ARE WORKING FOR

This is FinPilot AI, a full-stack financial management platform that integrates
with TallyPrime (Indian accounting software) via a local connector.

- Backend: FastAPI + SQLAlchemy + PostgreSQL, deployed on Render
- Frontend: React + TypeScript + Tailwind, deployed on Render
- Connector: Python script running locally on the user's PC, talks to TallyPrime HTTP server
- Only one user/company is using this right now — no multi-tenant concerns during migration

---

## PART 1 — VOUCHER MODEL MIGRATION

### The Problem

The `Expense` model is being abused to store voucher entries that are NOT expenses:
Receipt, Payment, Journal, Contra, Credit Note, Debit Note, and all Custom voucher
types (e.g. "GST Bill"). This causes:
- Party stored in `notes` string ("Party: ABC Traders | Type: GST Bill") — not queryable
- No FK to `TallyVoucherType` for custom types
- Semantic confusion: a Receipt is not an Expense

### Current Model Map

| Voucher Type        | Currently stored in | How identified                     |
|---------------------|--------------------|------------------------------------|
| Sales               | `Invoice`          | `invoice_type = SALES`             |
| Purchase            | `Invoice`          | `invoice_type = PURCHASE`          |
| Receipt             | `Expense`          | `category = "Receipt"`             |
| Payment             | `Expense`          | `category = "Payment"`             |
| Journal             | `Expense`          | `category = "Journal"`             |
| Contra              | `Expense`          | `category = "Contra"`              |
| Credit Note         | `Expense`          | `category = "Credit Note"`         |
| Debit Note          | `Expense`          | `category = "Debit Note"`          |
| Custom (e.g. GST Bill) | `Expense`       | `category = custom type name`      |
| Actual Expense      | `Expense`          | `category = null / standard cat`   |

### New `Voucher` Model

Create `backend/app/models/voucher.py`:

```python
class Voucher(Base):
    __tablename__ = "vouchers"

    id              = Column(UUID, primary_key=True, default=uuid4)
    company_id      = Column(UUID, FK("companies.id"), nullable=False, index=True)
    created_by      = Column(UUID, FK("users.id"), nullable=True)

    voucher_type    = Column(String(50), nullable=False)
    # Standard values: "Receipt" | "Payment" | "Journal" | "Contra" |
    #                  "Credit Note" | "Debit Note"
    # Custom: the custom type name exactly (e.g. "GST Bill")

    custom_type_id  = Column(UUID, FK("tally_voucher_types.id"), nullable=True)
    # Set only for custom voucher types — gives access to parent type

    date            = Column(DateTime(timezone=True), nullable=False)
    narration       = Column(Text, nullable=True)
    amount          = Column(Numeric(15, 2), nullable=False, default=0)

    # Ledger fields — populated based on voucher_type
    party_ledger    = Column(String(255), nullable=True)   # Receipt, Payment, Credit Note, Debit Note, Custom
    account_ledger  = Column(String(255), nullable=True)   # Receipt, Payment (bank/cash account)
    sales_ledger    = Column(String(255), nullable=True)   # Credit Note, Custom(Sales)
    purchase_ledger = Column(String(255), nullable=True)   # Debit Note, Custom(Purchase)
    dr_ledger       = Column(String(255), nullable=True)   # Journal
    cr_ledger       = Column(String(255), nullable=True)   # Journal
    from_account    = Column(String(255), nullable=True)   # Contra
    to_account      = Column(String(255), nullable=True)   # Contra

    tally_voucher_ref  = Column(String(100), nullable=True)
    tally_sync_status  = Column(String(50), default="local_only")
    # values: local_only | pending | synced | failed | delete_pending | delete_failed

    source          = Column(String(50), default="finpilot")
    # values: finpilot | tally_sync

    is_deleted      = Column(Boolean, default=False)
    created_at      = Column(DateTime(timezone=True), default=utcnow)
    updated_at      = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    # Relationships
    custom_type     = relationship("TallyVoucherType")
```

### Migration Steps

1. **Alembic migration** — creates `vouchers` table and migrates data:
   - INSERT into `vouchers` all `Expense` rows where `category` IN
     ('Receipt', 'Payment', 'Journal', 'Contra', 'Credit Note', 'Debit Note')
     OR where `category` matches any name in `tally_voucher_types`
   - For party: parse `notes` field: `notes.split("Party: ")[1].split(" |")[0].strip()`
   - For custom types: look up `custom_type_id` from `tally_voucher_types` by name
   - DELETE those rows from `expenses` after inserting
   - Real expenses (null category / standard expense categories) stay in `expenses`

2. **`backend/app/api/v1/endpoints/assistant.py`** — `create_entity()` function:
   - Replace ALL `Expense(category="Receipt")` / `Expense(category="Payment")` etc.
     with `Voucher(voucher_type="Receipt")` etc.
   - Replace `Expense(category=vt_record.name)` for custom_voucher with
     `Voucher(voucher_type=vt_record.name, custom_type_id=vt_record.id, party_ledger=...)`
   - Store ledger fields as proper columns, not in `notes`

3. **`backend/app/api/v1/endpoints/management.py`** — `list_vouchers()`:
   - Query `Voucher` model instead of `Expense` for non-expense types
   - `voucher_type=CUSTOM` → filter `Voucher` where `custom_type_id IS NOT NULL`
   - Return `party_ledger` directly instead of parsing `notes`
   - Return `custom_type.name` and `custom_type.parent` from the FK relationship

4. **`backend/app/api/v1/endpoints/tally.py`** — `submit_job_result()`:
   - CANCEL_VOUCHER and voucher CREATE handlers look up by `tally_voucher_ref`
   - Add `Voucher` to the lookup alongside `Invoice` and `Expense`
   - Keep `Expense` lookup as fallback for any records created before migration

5. **Frontend** `frontend/src/types/index.ts` — `VoucherItem`:
   - `party_name` should come from `party_ledger` directly (no more notes parsing)
   - `custom_type_name` and `parent_type` are proper fields, not optional hacks

---

## PART 2 — VOUCHER CRUD UI IN ACCOUNTING TABS

### The Problem

Currently, voucher entries (Receipt, Payment, Journal, Contra, Credit Note, Debit Note,
and Custom types) can ONLY be created from the **AI Create page**
(`/ai-create` → "Create with AI"). There is no way to create them manually from the
**Accounting → Vouchers** page tabs.

The Vouchers page (`frontend/src/pages/accounting/VouchersPage.tsx`) only lists
existing entries — it has no Create button for any tab.

### Goal

Each tab in the Vouchers page should have a **"+ New [Type]"** button that opens
a form/dialog to create that voucher type directly, without going through AI.
The created entry must:
1. Save to the FinPilot database (new `Voucher` model after migration, or current `Expense` if migration hasn't run yet)
2. Queue a Tally sync job so it appears in TallyPrime
3. Show immediately in the tab list

### Tabs and Forms Required

Each tab needs its own form fields:

**Sales** — handled by Invoice, skip (already has its own flow)

**Purchase** — handled by Invoice, skip

**Receipt** (money received FROM customer)
- Party Ledger (text, required) — who paid you
- Account Ledger (text, required, default "Cash") — which bank/cash account
- Amount (number, required)
- Date (date picker, default today)
- Narration (text)

**Payment** (money paid TO vendor)
- Party Ledger (text, required) — who you paid
- Account Ledger (text, required, default "Cash") — from which bank/cash account
- Amount (number, required)
- Date (date picker, default today)
- Narration (text)

**Journal** (general Dr/Cr entry)
- Dr Ledger (text, required) — debit side ledger
- Cr Ledger (text, required) — credit side ledger
- Amount (number, required)
- Date (date picker, default today)
- Narration (text)

**Contra** (bank ↔ cash transfer)
- From Account (text, required, default "Cash")
- To Account (text, required, default "Bank")
- Amount (number, required)
- Date (date picker, default today)
- Narration (text)

**Credit Note** (sales return)
- Party Ledger (text, required) — customer returning goods
- Sales Ledger (text, required, default "Sales")
- Amount (number, required)
- Date (date picker, default today)
- Narration (text)

**Debit Note** (purchase return)
- Party Ledger (text, required) — supplier goods returned to
- Purchase Ledger (text, required, default "Purchases")
- Amount (number, required)
- Date (date picker, default today)
- Narration (text)

**✨ Custom** tab
- Voucher Type Name (dropdown, list from `managementApi.voucherTypes()` filtered to custom only)
- Then show fields based on the selected type's parent (same fields as above)
- Amount (number, required)
- Date (date picker, default today)
- Narration (text)

### Backend — New Endpoint Needed

Add to `backend/app/api/v1/endpoints/management.py`:

```
POST /management/vouchers
```

Body:
```json
{
  "voucher_type": "Receipt",          // or "Payment", "Journal", etc. or custom name
  "custom_type_id": "uuid-or-null",   // null for standard types
  "date": "2026-08-16",
  "party_ledger": "ABC Traders",
  "account_ledger": "Cash",
  "sales_ledger": "Sales",
  "purchase_ledger": "Purchases",
  "dr_ledger": "Salary Expenses",
  "cr_ledger": "Cash",
  "from_account": "Cash",
  "to_account": "HDFC Bank",
  "amount": 25000,
  "narration": "GST Invoice Aug 2026"
}
```

This endpoint should:
1. Create a `Voucher` record (or `Expense` if migration not done yet)
2. Call `queue_tally_write()` with the appropriate operation + payload
3. Return `{ "id": "...", "tally_queued": true/false }`

### Frontend — API + UI

Add to `frontend/src/api/endpoints.ts`:
```typescript
managementApi.createVoucher(data: CreateVoucherRequest): Promise<{ id: string; tally_queued: boolean }>
```

In `VouchersPage.tsx`:
- Each tab (except Sales/Purchase) shows a `+ New Receipt` / `+ New Payment` etc. button top-right
- Clicking opens a Dialog with the relevant form fields
- On submit: call `managementApi.createVoucher()`, invalidate `['vouchers']` query, show toast
- Custom tab: dropdown first to pick the custom type, then show appropriate fields

### UX Details

- Date picker defaults to today's date
- All ledger fields are free-text (not dropdowns) — TallyPrime ledger names vary per company
- After creation, row appears immediately in the list with sync status "pending"
- If Tally connector is offline, still save to DB and show "local_only" sync status
- Form resets after successful create, dialog stays open so user can add another entry

---

## FILES TO MODIFY (COMPLETE LIST)

### Backend
- `backend/app/models/voucher.py` — CREATE new file
- `backend/alembic/versions/XXXX_add_vouchers_table.py` — CREATE migration
- `backend/app/api/v1/endpoints/assistant.py` — UPDATE create_entity() for all voucher types
- `backend/app/api/v1/endpoints/management.py` — UPDATE list_vouchers(), ADD create_voucher()
- `backend/app/api/v1/endpoints/tally.py` — UPDATE submit_job_result() cancel/sync handlers
- `backend/app/api/v1/router.py` — check Voucher model is imported/registered if needed
- `backend/app/db/base.py` — import Voucher so SQLAlchemy sees it

### Frontend
- `frontend/src/types/index.ts` — UPDATE VoucherItem, ADD CreateVoucherRequest
- `frontend/src/api/endpoints.ts` — ADD managementApi.createVoucher()
- `frontend/src/pages/accounting/VouchersPage.tsx` — ADD create forms per tab

---

## WHAT NOT TO TOUCH

- `Invoice` model and its endpoints — leave completely alone
- `Expense` model — keep it, just stop using it for voucher-type records
- `tally_client.py` in `tally-connector/` — do not modify
- `connector.py` in `tally-connector/` — do not modify
- Any existing alembic migrations — only ADD a new one, never edit old ones

---

## DEFINITION OF DONE

- [ ] `vouchers` table in DB with all fields
- [ ] Existing Receipt/Payment/Journal/Contra/CreditNote/DebitNote/Custom Expense rows migrated
- [ ] `Expense` table contains only real expenses after migration
- [ ] AI Create page still works for all voucher types (uses new Voucher model)
- [ ] Accounting → Vouchers → Receipt tab has "+ New Receipt" button → form → creates entry
- [ ] Same for Payment, Journal, Contra, Credit Note, Debit Note tabs
- [ ] Custom tab has dropdown to pick custom type → appropriate fields → creates entry
- [ ] All created entries show in their respective tab immediately
- [ ] All created entries queue a Tally sync job (connector picks it up and sends to TallyPrime)
- [ ] CANCEL_VOUCHER still works for both old Expense records and new Voucher records
- [ ] No 500 errors in production after deployment
