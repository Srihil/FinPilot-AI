# FinPilot AI — Full Project Capabilities

**As of:** 2026-08-15  
**Live URL:** https://finpilot-frontend-vbdf.onrender.com  
**GitHub:** https://github.com/Srihil/FinPilot-AI  
**Stack:** React 18 + TypeScript + Vite (frontend) / Python 3.12 + FastAPI + PostgreSQL (backend) / Python Windows app (Tally Connector)

---

## What This Project Is

FinPilot AI is a full-stack, production-deployed AI-powered finance and accounting platform for small and medium businesses. It has two core halves:

1. **FinPilot Cloud** — a web application for managing finances, asking AI questions, creating records via natural language, and viewing analytics + reports.
2. **TallyPrime Connector** — a downloadable Windows desktop app that bridges the cloud platform with TallyPrime (India's most widely used accounting software) running on a user's local PC.

The platform is live on Render (free tier) with a PostgreSQL database, a FastAPI backend, and a static React frontend.

---

## Unstaged / Untracked Files (not yet committed)

| File | What it is |
|------|-----------|
| `start-connector.bat` | One-click launcher for the Tally Connector in Python mode (installs deps, runs `app.py`) |
| `tally-connector/FinPilot-Connector.spec` | PyInstaller spec for building the GUI connector (`app.py`) into a `.exe` |
| `tally-connector/finpilot-tally-connector.spec` | PyInstaller spec for the headless/terminal connector into a `.exe` |

---

## 1. Authentication & Access Control

- **JWT-based auth** — access tokens (24h default expiry), bcrypt password hashing, never stored plain
- **Three roles:**
  - `ADMIN` — full access, can approve transactions, manage Tally connector, change settings
  - `ACCOUNTANT` — can create and view all records, cannot approve
  - `VIEWER` — read-only access
- **Multi-tenant isolation** — every DB query is filtered by `company_id`; users cannot see data from other companies
- **Signup flow** — creates a new company + admin user in one step
- **Demo credentials** (seeded): `admin@acmemfg.in` / `Admin@123` (Acme Manufacturing Pvt. Ltd.)

---

## 2. Dashboard

- **Real-time KPIs:** Total Revenue, Total Expenses, Net Profit, Accounts Receivable, Accounts Payable — all computed from live DB data
- **12-month Revenue vs Expenses chart** (Recharts line chart)
- **Recent Transactions** list with status badges
- **Low Stock Alerts** for products below threshold
- All data is company-scoped and updates on every page visit

---

## 3. AI Finance Assistant

**Conversational AI** that answers questions about your own financial data.

- **Multi-conversation** — create, rename, delete conversations; full chat history preserved
- **Real data access** — AI uses controlled read-only tools to query actual DB (not hallucinated answers):
  - Revenue by period, expense breakdown, top customers, outstanding receivables, payables
  - Invoice lists, expense categories, product inventory
- **AI Provider switching** — backend supports Groq (default: `llama-3.3-70b-versatile`) and OpenRouter (`google/gemma-4-26b-a4b-it:free`). Falls back to demo rule-based mode if no API key
- **Tool-calling pattern** — AI decides which finance tool to call, gets structured data, then explains it in natural language
- **Demo mode** — fully functional without any API key using rule-based pattern matching on real data

---

## 4. AI Transaction Proposal (Approve/Reject Flow)

- User describes a transaction in plain English (e.g., "Record ₹50,000 payment from ABC Corp for invoice #45")
- AI uses `TransactionAgent` to extract a structured proposal: type, parties, amounts, dates
- Proposal is validated and shown to the user as a preview card
- User can **approve** or **reject** — approval commits the record to DB
- Full **audit trail** of every proposal, approval decision, and who made it

---

## 5. Create with AI (AI Create Page)

The most powerful feature for TallyPrime users. Describe anything in plain English and the AI extracts structured data, lets you edit it, then creates it in FinPilot and queues it for sync to TallyPrime.

### Supported Entity Types

**Accounting Masters:**
| Entity | What it creates |
|--------|----------------|
| `ledger` | TallyPrime ledger account (name, group like Sundry Debtors/Creditors/Bank Accounts, opening balance) |
| `group` | TallyPrime account group (name, parent like Capital Account/Current Assets) |
| `customer` | FinPilot Customer record + TallyPrime ledger under Sundry Debtors |
| `vendor` | FinPilot Vendor record + TallyPrime ledger under Sundry Creditors |

**Inventory Masters:**
| Entity | What it creates |
|--------|----------------|
| `stock_item` / `product` | FinPilot Product + TallyPrime stock item (name, unit, selling price) |
| `stock_group` | TallyPrime stock group (name, parent — empty = top-level root) |
| `unit` | TallyPrime unit of measure (symbol auto-sanitized: no spaces, max 8 chars) |
| `godown` | TallyPrime warehouse/godown (name, parent location) |

**Vouchers (Transactions):**
| Entity | What it creates |
|--------|----------------|
| `sales_invoice` | FinPilot invoice + TallyPrime Sales voucher |
| `purchase_bill` | FinPilot invoice + TallyPrime Purchase voucher |
| `receipt` | TallyPrime Receipt voucher (party → cash/bank) |
| `payment` | TallyPrime Payment voucher (cash/bank → party) |
| `journal` | TallyPrime Journal voucher (Dr ledger, Cr ledger) |
| `credit_note` | TallyPrime Credit Note (sales return) |
| `debit_note` | TallyPrime Debit Note (purchase return) |
| `contra` | TallyPrime Contra voucher (bank/cash transfer) |
| `expense` | FinPilot Expense + TallyPrime Purchase voucher |

### How AI Create Works
1. User types in plain English OR picks a quick-start chip
2. Backend calls `EntityAgent` (Groq/OpenRouter LLM) → returns `{entity_type, data, confidence, missing_fields}`
3. Frontend shows an **editable preview** with confidence bar and missing field warnings
4. User clicks "Create & Sync to Tally" → entity saved in FinPilot DB + Tally write job queued
5. **Activity Drawer** (right-side slide-in panel) shows real-time sync status

### Tally Activity Drawer
- Always visible as a floating tab on the right edge of the screen
- Status dot: red (failed), amber (pending/processing), green (all synced)
- Shows all jobs latest-first with: operation name, status badge, time ago, retry count
- **Smart error messages** translate raw Tally errors into plain-English advice:
  - `BAD UNIT NAME` → "Use short abbreviations like Nos/Kgs/Pcs with no spaces"
  - `Stock Group 'Primary' does not exist` → "The root group is implicit; create without a parent"
  - `Ledger 'X' does not exist` → "Create ledger X in TallyPrime first"
  - `Already exists` → "Entry already in TallyPrime, no action needed"
- Polls every 5 seconds when open, every 20 seconds when closed

---

## 6. TallyPrime Integration

### Architecture
```
Browser (React) → FinPilot Cloud (Render) ← HTTPS polling ← Connector App (Windows PC) → TallyPrime localhost:9000
```
TallyPrime is never directly exposed to the internet. The connector polls the cloud for jobs.

### Connector App (`tally-connector/`)
- **GUI Desktop App** (`app.py`) — system tray app with tkinter pairing window
  - Shows pairing code entry field, connection status, TallyPrime company name
  - System tray icon with colour-coded status dot (green = online, red = error)
  - "Open FinPilot" tray menu item → opens browser to live site
  - Handles Windows Defender/SmartScreen download warnings
  - Auto-handles Render cold-start delays (70s timeout with user-friendly hint)
- **Headless Connector** (`connector.py`) — terminal version, same polling logic, no GUI
- **Start Script** (`start-connector.bat`) — one-click Python launcher (unstaged)
- **PyInstaller specs** — two `.spec` files for building GUI and headless `.exe` bundles (unstaged)

### Pairing Flow
1. Admin generates a 9-character pairing code in the web app (TallyPrime page)
2. User enters the code in the Connector app's pairing window
3. Connector registers with the cloud, receives a bcrypt-hashed bearer token
4. Heartbeat runs every 15s (configurable) — updates connector online status
5. Cloud shows connector status: online/offline, last heartbeat, TallyPrime company name

### Job Queue System
- Jobs created in `tally_integration_jobs` table with statuses: `PENDING → CLAIMED → SUCCESS/FAILED/RETRYING`
- Connector polls `/api/tally/connector/jobs` → claims PENDING jobs → executes → submits result
- **Idempotency keys** prevent duplicate writes even if connector crashes mid-run
- **Auto-retry** up to 3 times on failure, then marks `FAILED`
- **Approval gate** — write operations can be gated behind an Approval record (ADMIN-only flow)

### Read Operations (Tally → FinPilot)
| Operation | What it fetches |
|-----------|----------------|
| `READ_LEDGERS` | All ledgers with name, parent group, closing balance |
| `READ_VOUCHERS` | All vouchers (date, type, party, amount, narration) via inline TDL |
| `READ_SALES` | Filtered Sales vouchers |
| `READ_PURCHASES` | Filtered Purchase vouchers |
| `READ_RECEIVABLES` | Sundry Debtor ledger balances |
| `READ_PAYABLES` | Sundry Creditor ledger balances |
| `READ_STOCK_ITEMS` | Inventory items with closing balance and rate |
| `READ_COMPANIES` | Active company name |

### Write Operations (FinPilot → Tally)
All write ops use TallyPrime's HTTP XML import API (`POST http://localhost:9000`):

| Operation | TallyPrime XML object |
|-----------|----------------------|
| `CREATE_LEDGER` | `<LEDGER ACTION="Create">` with NAME, PARENT, OPENINGBALANCE |
| `CREATE_GROUP` | `<GROUP ACTION="Create">` with NAME, PARENT |
| `CREATE_STOCK_ITEM` | `<STOCKITEM ACTION="Create">` with NAME, PARENT, BASEUNITS |
| `CREATE_STOCK_GROUP` | `<STOCKGROUP ACTION="Create">` with NAME, PARENT (empty = root) |
| `CREATE_UNIT` | `<UNIT ACTION="Create">` with NAME, ORIGINALNAME (sanitized symbol), DECIMALPLACES, UOMTYPE=Simple |
| `CREATE_GODOWN` | `<GODOWN ACTION="Create">` with NAME, PARENT |
| `CREATE_SALES_VOUCHER` | Sales voucher with party debit + sales credit entries |
| `CREATE_PURCHASE_VOUCHER` | Purchase voucher with party credit + purchase debit entries |
| `CREATE_RECEIPT_VOUCHER` | Receipt: cash/bank Dr, party Cr |
| `CREATE_PAYMENT_VOUCHER` | Payment: party Dr, cash/bank Cr |
| `CREATE_JOURNAL_VOUCHER` | Journal: dr_ledger Dr, cr_ledger Cr |
| `CREATE_CREDIT_NOTE` | Credit Note (sales return): sales Dr, party Cr |
| `CREATE_DEBIT_NOTE` | Debit Note (purchase return): party Dr, purchase Cr |
| `CREATE_CONTRA_VOUCHER` | Contra: to_account Dr, from_account Cr |
| `SYNC_FULL` | Full data sync: reads all ledgers + vouchers + stock items |

### Two-Way Data Sync (`SYNC_FULL`)
When a full sync job completes, `tally_sync_service` processes the result:
- **Tally Ledgers → FinPilot Customers/Vendors** based on parent group (Sundry Debtors → Customer, Sundry Creditors → Vendor)
- **Tally Sales Vouchers → FinPilot Invoices** (SALES type)
- **Tally Purchase Vouchers → FinPilot Expenses** (tagged `[tally-sync]`)
- **Deduplication endpoint** (`POST /api/tally/dedup`) removes duplicate sync-created records
- Activity visible under TallyPrime → Interaction Activity in the web app

### XML Safety
- `defusedxml` used for parsing (XXE protection)
- Custom sanitizer strips TallyPrime's illegal XML control characters (U+0000–U+001F)
- REMOTEID + VOUCHERNUMBER + EFFECTIVEDATE added to all voucher XML for proper tracking

---

## 7. Customer Management

- Full CRUD: create, view, edit, delete customers
- Fields: name, email, phone, address, city, state, GST number, notes
- Search + pagination
- Per-customer revenue tracking and outstanding receivables display
- Customers created via AI Create automatically get a Sundry Debtors ledger queued in Tally

---

## 8. Vendor Management

- Full CRUD: create, view, edit, delete vendors
- Same fields as customers (name, email, phone, GST, etc.)
- Outstanding payables display
- Vendors created via AI Create automatically get a Sundry Creditors ledger queued in Tally

---

## 9. Inventory / Products

- Full product catalog with: name, SKU, selling price, cost price, unit, stock quantity
- Low-stock alerts on dashboard when quantity falls below a threshold
- Products created via AI Create queue a `CREATE_STOCK_ITEM` in Tally

---

## 10. Transactions

- **Invoices:** SALES and PURCHASE types, full item line support, status lifecycle (draft → approved → paid)
- **Expenses:** Title, category, amount, tax, vendor link, date, status (draft/approved/paid)
- Filter by type, status; paginated list
- Invoices and expenses created via AI Create queue the appropriate Tally voucher

---

## 11. Approval Center

- All AI-proposed transactions and writes go into an Approvals queue
- ADMIN can approve or reject with notes
- `ApprovalStatus`: PENDING → APPROVED / REJECTED
- Tally write operations that require an approval check the `approval_id` is in APPROVED state before queuing
- Accountants can create proposals; only Admins approve

---

## 12. Bulk Uploads

- **CSV/XLSX upload** for customers, vendors, products, invoices, expenses
- File validation: size limit (10 MB), column mapping, error reporting per row
- Preview before import: shows valid rows, skipped rows, error messages
- **PDF Invoice extraction** — upload a PDF bill and AI extracts structured invoice data

---

## 13. Analytics

- Date-range filtered overview: Revenue, Expenses, Profit, Invoice count
- Charts: Revenue by month, Expense by category (pie chart), Top customers, Top vendors
- Computed from live DB queries (not cached snapshots)

---

## 14. PDF Reports

- Generate downloadable PDF reports:
  - **Profit & Loss** (P&L)
  - **Revenue Report**
  - **Expense Report**
  - **Receivables Report**
- Built with ReportLab, full Unicode support including ₹ (Rupee symbol)
- Correct PDF metadata: title, author (company name), subject, creator = "FinPilot AI"
- Downloadable from the Reports page (browser save dialog)
- Report history stored in DB

---

## 15. Audit Logs

- Every significant action is logged: CREATE, UPDATE, DELETE, APPROVE, REJECT, AI_QUERY, AI_PROPOSAL, INTEGRATION_SYNC, SETTINGS_CHANGE
- Fields: user, company, entity_type, entity_id, action, description, timestamp
- Paginated, read-only view in the UI

---

## 16. Settings

- **Company Settings:** name, address, GST number, contact info
- **AI Provider Settings:** switch between Groq and OpenRouter without editing environment variables; selected model stored per company in DB
- Default AI model: Groq `llama-3.3-70b-versatile`
- Fallback chain: Groq → OpenRouter → Demo (rule-based, no API key needed)

---

## 17. TallyPrime Page (Connector Management)

- **Pairing:** Generate 9-char pairing code (valid 15 minutes), show QR-style display for user to enter in Connector app
- **Status panel:** Real-time online/offline indicator, last heartbeat time, TallyPrime company name, connector device name
- **Sync button:** Triggers `SYNC_FULL` job immediately
- **Interaction Activity:** Paginated table of all Tally jobs with status, operation name, timestamp, error messages
- **Dedup:** Remove duplicate sync-created records button
- **Disconnect:** Revoke the connector token (ADMIN only)
- **Download Connector:** Button to download the `.exe` installer from GitHub Releases (fetches latest release, bypasses browser cache with `?t=timestamp`)

---

## 18. Deployment

| Component | Platform | Notes |
|-----------|----------|-------|
| Frontend | Render Static Site | `npm run build` → `dist/`, all routes rewrite to `index.html` |
| Backend | Render Web Service (free) | `alembic upgrade head && python -m app.db.seed && uvicorn app.main:app` |
| Database | Render PostgreSQL (free) | Auto-connected via `DATABASE_URL` env var |
| Connector | Windows PC (local) | `.exe` or Python script, connects via HTTPS to Render backend |

- **Render blueprint** (`render.yaml`) defines all three services with env vars
- Migrations run automatically on every deploy (`alembic upgrade head`)
- Demo data seeded on every deploy (`python -m app.db.seed`)
- CORS configured for the live frontend URL
- Health check endpoint: `GET /health`
- AI API keys (`GROQ_API_KEY`, `OPENROUTER_API_KEY`) set manually in Render dashboard

---

## 19. Database Schema (Key Tables)

| Table | Purpose |
|-------|---------|
| `companies` | Multi-tenant root — every other table has `company_id` FK |
| `users` | Auth + RBAC (`admin/accountant/viewer`) |
| `customers` | Customer master |
| `vendors` | Vendor master |
| `products` | Inventory / stock items |
| `invoices` + `invoice_items` | Sales and purchase invoices |
| `expenses` | Expense records |
| `approvals` | Approval queue for writes |
| `ai_conversations` + `ai_messages` | Chat history |
| `audit_logs` | Full action history |
| `reports` | Generated report metadata |
| `uploads` | Bulk upload history |
| `tally_connectors` | Registered connector tokens (bcrypt-hashed) |
| `tally_pairing_codes` | One-time pairing codes (TTL-based) |
| `tally_integration_jobs` | Job queue: all Tally read/write operations |

**Migration chain:** `b05e77fbce20` → `c1a2b3d4e5f6` → `d7e8f9a0b1c2` → `e9f0a1b2c3d4`

---

## 20. Testing

- **29 connector unit tests** (`tally-connector/tests/`) — cover all read/write operations, XML parsing, error handling
- **22 backend Tally integration tests** (`backend/tests/test_tally.py`)
- Key security invariants verified by tests:
  - Company A cannot read Company B data
  - VIEWER cannot create/modify financial records
  - Only ADMIN can approve transactions
  - AI tools cannot execute arbitrary database writes
  - Connector token auth rejects invalid tokens

---

## 21. Known Bugs Fixed (Recent)

| Bug | Fix |
|----|-----|
| `BAD UNIT NAME` from TallyPrime | Unit symbol now stripped of spaces and capped at 8 chars before sending XML |
| `Stock Group 'Primary' does not exist` | Default parent for stock groups changed from `"Primary"` to `""` (empty = implicit root) |
| Voucher errors: missing REMOTEID, EFFECTIVEDATE, VOUCHERNUMBER | All voucher XML now includes all three required fields |
| AI returning `"voucher"` as entity_type | Entity agent system prompt and create_entity both normalise "voucher" → specific type |
| Tally sync creating duplicate records on each sync | Dedup endpoint + idempotency logic by notes key |
| TallyPrime EDU company name showing as `0` | Improved `_extract_company_name` checks multiple XML paths, skips numeric values |
| Groq `tool_use_failed` breaking assistant | Switched to `llama-3.1-8b-instant`; better error handling |
| PDF Rupee symbol showing as black box on second download | Font registry check before re-registering Arial; correct Unicode font always returned |
| GitHub Releases `.exe` download using browser cache | Cache-busted with `?t=timestamp` query param |

---

## 22. Security Architecture

- **Passwords:** bcrypt, never stored plain
- **Connector tokens:** bcrypt-hashed, never retrievable after pairing
- **JWT:** Short-lived, company-scoped, role-enforced at API level (not just frontend)
- **Multi-tenant:** Every single DB query filtered by `company_id` — no cross-company leakage
- **AI tools are read-only and strongly typed** — LLM cannot run arbitrary SQL
- **Write safety:** All financial writes require either human approval or AI Create flow with explicit commit step
- **Tally write safety:** Connector only processes known operations from `ALLOWED_OPS` set; all others rejected
- **XXE protection:** `defusedxml` used for all XML parsing from TallyPrime
- **No TallyPrime exposure:** TallyPrime's local HTTP port is never accessible from the internet

---

## 23. AI Provider Configuration

| Provider | Model | Notes |
|---------|-------|-------|
| Groq (default) | `llama-3.3-70b-versatile` | Finance assistant; fast, free tier |
| Groq | `llama-3.1-8b-instant` | Entity extraction agent |
| OpenRouter | `google/gemma-4-26b-a4b-it:free` | Alternative to Groq |
| Demo | Rule-based | Works with zero API keys |

Switching provider: Settings → AI Config → select provider → saved per company in DB.

---

## 24. Frontend Pages Summary

| Route | Page | Description |
|-------|------|-------------|
| `/dashboard` | Dashboard | KPIs, charts, alerts |
| `/assistant` | AI Assistant | Multi-conversation finance chat |
| `/ai-create` | Create with AI | NL → entity extraction → create + Tally sync |
| `/transactions` | Transactions | Invoices + expenses list |
| `/customers` | Customers | Full CRUD |
| `/vendors` | Vendors | Full CRUD |
| `/inventory` | Inventory | Product catalog |
| `/uploads` | Bulk Uploads | CSV/PDF import |
| `/analytics` | Analytics | Date-range charts |
| `/reports` | Reports | Generate + download PDFs |
| `/approvals` | Approvals | Approve/reject queue |
| `/audit-logs` | Audit Logs | Full action history |
| `/tally` | TallyPrime | Connector management + activity |
| `/settings` | Settings | Company info + AI provider |

---

## 25. What's NOT Yet Built (Future Scope)

- Individual pages/management for Tally-only masters (Ledgers, Units, Stock Groups, Godowns, Voucher lists)
- GST return filing integration
- Bank reconciliation
- Email/WhatsApp invoice delivery
- Multi-currency support
- Budget vs actuals tracking
- Automated overdue reminders
- Mobile app
- Real-time push notifications (currently polling-based)
- Delete/modify records in TallyPrime via FinPilot (TallyPrime XML API has limited delete support)
