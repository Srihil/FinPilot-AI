# FinPilot AI

**AI-Powered Finance Operations & TallyPrime Integration Platform**

FinPilot AI is a full-stack, production-deployed web application for small and medium businesses in India. It combines an AI finance assistant, complete accounting record management, and a deep two-way sync with TallyPrime — all with human approval required for every financial write.

**Live:** https://finpilot-frontend-vbdf.onrender.com  
**GitHub:** https://github.com/Srihil/FinPilot-AI

---

## What This Project Is

FinPilot AI has two halves that work together:

1. **FinPilot Cloud** — a React + FastAPI web app for managing finances, asking AI questions, creating records via natural language, and syncing everything to TallyPrime.
2. **TallyPrime Connector** — a Windows desktop/terminal app that runs on the same PC as TallyPrime and bridges it to the cloud over HTTPS (TallyPrime is never exposed to the internet).

---

## Features

### AI Finance Assistant
- Conversational AI that answers questions about your own financial data (not hallucinated answers)
- Multi-conversation: create, rename, delete conversations; full chat history
- AI uses controlled read-only tools to query the actual database: revenue, expenses, top customers, receivables, payables, inventory
- Multi-provider: **Groq** (`llama-3.3-70b-versatile`), **OpenRouter** (`gemma-4-26b`), or **Demo mode** (rule-based, no API key needed)
- Switch providers live from Settings without touching environment variables

### Create with AI (Natural Language → TallyPrime)
Describe anything in plain English and the AI extracts structured data, shows an editable preview, then creates it in FinPilot and queues it for sync to TallyPrime.

**Supported entity types:**

| Category | Entities |
|----------|---------|
| Accounting Masters | Ledger, Group, Customer (Sundry Debtors), Vendor (Sundry Creditors) |
| Inventory Masters | Stock Item / Product, Stock Group, Unit of Measure, Godown |
| Vouchers | Sales Invoice, Purchase Bill, Receipt, Payment, Journal, Credit Note, Debit Note, Contra, Expense |

### TallyPrime Two-Way Sync

**Read (Tally → FinPilot):**
- Ledgers with closing balances
- All vouchers (sales, purchase, receipts, payments, journals, etc.)
- Stock items with parent groups and closing balances
- Stock transactions (stock journals, physical stock, delivery notes, receipt notes)
- Outstanding receivables and payables
- Active company name

**Write (FinPilot → Tally):**
- Create and alter all master types (ledger, group, stock item, stock group, unit, godown)
- Create all voucher types (sales, purchase, receipt, payment, journal, credit note, debit note, contra)
- Ledgers include GSTIN (`LEDGSTREGDETAILS.LIST`), address, and state (`LEDMAILINGDETAILS.LIST`) for full TallyPrime field population
- ALTER operations use the old name as the identifier — no duplicate creation on rename
- Delete vouchers from TallyPrime using REMOTEID tracking
- Full sync (`SYNC_FULL`): wipes and rebuilds all vouchers/stock transactions from TallyPrime as source of truth

### Voucher CRUD (Vouchers Page)
- Create, view, edit, and delete all voucher types from within FinPilot
- Full ledger dropdowns sourced from synced TallyPrime data
- Expandable rows with narration, amount, party name, status
- Edit flow sends `ACTION=Alter` to TallyPrime; delete uses REMOTEID for tracking across wipe+resync

### Dashboard
- Real-time KPIs: Revenue, Expenses, Net Profit, Accounts Receivable, Accounts Payable
- 12-month Revenue vs Expenses chart
- Recent transactions list with status badges
- Low-stock alerts

### Approval Center
- All AI-proposed transactions enter an Approvals queue
- ADMIN approves or rejects with notes
- Tally write operations can be gated behind approval status

### Bulk Uploads
- CSV / XLSX import for customers, vendors, products, invoices, expenses
- Row-level validation with error reporting and preview before commit
- PDF invoice upload — AI extracts structured invoice data

### PDF Reports
- Downloadable P&L, Revenue, Expense, and Receivables reports
- Built with ReportLab; full Unicode support including ₹ symbol
- Correct PDF metadata: title, author (company name), creator = "FinPilot AI"

### Standard Accounting Modules
- **Customers & Vendors** — full CRUD, GST number, address, revenue/outstanding tracking
- **Inventory** — product catalog, SKU, pricing, stock quantity, low-stock alerts
- **Transactions** — invoices (sales/purchase) and expenses with full status lifecycle
- **Analytics** — date-range filtered charts: revenue by month, expenses by category, top customers/vendors
- **Audit Logs** — every action logged with user, timestamp, entity, and description
- **Settings** — company info, AI provider selection, Tally connector management

---

## TallyPrime Connector

### Architecture

```
Browser → FinPilot Cloud (Render) ← HTTPS polling ← Connector App (Windows PC) → TallyPrime localhost:9000
```

TallyPrime is never directly exposed to the internet. The connector only makes outbound HTTPS requests.

### Connector Types
- **GUI Desktop App** (`app.py`) — system tray app with tkinter pairing window, colour-coded status dot, "Open FinPilot" tray menu item
- **Headless Connector** (`connector.py`) — terminal version, same polling logic
- **Start Script** (`start.bat`) — one-click Python launcher (creates venv, installs deps, runs)
- **PyInstaller specs** — `.spec` files for building both variants into `.exe` bundles

### Pairing Flow
1. Admin generates a 9-character pairing code in the web app (valid 15 minutes)
2. User enters the code in the Connector app's pairing window
3. Connector registers with cloud, receives a bcrypt-hashed bearer token
4. Heartbeat every 15s — keeps connector online status current

### Job Queue
- Jobs: `PENDING → CLAIMED → SUCCESS / FAILED / RETRYING`
- Connector polls for jobs, claims and executes, submits results
- Idempotency keys prevent duplicate writes if connector crashes mid-run
- Auto-retry up to 3 times, then marks `FAILED`

### Tally Activity Drawer
- Global floating tab on the right edge of every page in the app
- Status dot: red (failed), amber (pending), green (all synced)
- Smart error messages translate raw Tally errors into plain-English advice
- Polls every 5s when open, every 20s when closed

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 17 |
| Auth | JWT (python-jose) + bcrypt password hashing |
| AI | Groq / OpenRouter / Demo mode |
| PDF | ReportLab (Unicode + ₹ symbol support) |
| File Processing | pandas, openpyxl, PyMuPDF |
| Testing | pytest (51 tests: 29 connector + 22 backend) |
| Deployment | Docker, Docker Compose, Render |
| XML Safety | defusedxml (XXE protection) |

---

## Security Model

- Passwords hashed with bcrypt — never stored plain
- Connector tokens bcrypt-hashed and never retrievable after pairing
- JWT tokens — company-scoped, role-enforced at API level (not just frontend)
- **Multi-tenant isolation** — every DB query filtered by `company_id`
- **AI tools are read-only and strongly typed** — LLM cannot run arbitrary SQL
- All financial writes require human approval or explicit AI Create commit step
- Connector only processes operations from an `ALLOWED_OPS` allowlist
- `defusedxml` used for all XML parsing from TallyPrime (XXE protection)
- Custom sanitizer strips TallyPrime's illegal XML control characters (U+0000–U+001F)

---

## Architecture

```
Browser (React)
    │ HTTPS / REST JSON
    ▼
FastAPI (Python)
    ├── JWT auth middleware
    ├── Company isolation filter (every query filtered by company_id)
    ├── Role-based authorization (ADMIN / ACCOUNTANT / VIEWER)
    │
    ├── API endpoints
    │   ├── /api/auth/*
    │   ├── /api/dashboard/*
    │   ├── /api/assistant/*      ← Finance AI Agent
    │   ├── /api/ai-create/*      ← Entity extraction + Tally job queue
    │   ├── /api/customers/*
    │   ├── /api/vendors/*
    │   ├── /api/products/*
    │   ├── /api/invoices/*
    │   ├── /api/expenses/*
    │   ├── /api/approvals/*
    │   ├── /api/analytics/*
    │   ├── /api/uploads/*
    │   ├── /api/reports/*
    │   ├── /api/audit-logs/*
    │   ├── /api/tally/*          ← Connector management, job queue, sync
    │   └── /api/settings/*
    │
    ├── Finance AI Agent
    │   ├── FinanceTools (controlled DB access — READ only)
    │   ├── GroqAgent / OpenRouterAgent / DemoAgent
    │   └── TransactionAgent (NL → structured proposal → human approval)
    │
    └── PostgreSQL (SQLAlchemy ORM + Alembic migrations)

AI Safety:
  READ  → FinanceAgent → typed tool → DB → LLM explanation
  WRITE → TransactionAgent → preview → Human approves → DB write → Audit log
  (The LLM never directly writes to the database)
```

---

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 17

### 1. Clone and configure

```bash
git clone https://github.com/Srihil/FinPilot-AI.git
cd FinPilot-AI
cp .env.example .env
# Edit .env — set DATABASE_URL and optionally an AI API key
```

### 2. Backend

**Windows (PowerShell):**
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Linux/macOS:**
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Database setup

```sql
CREATE DATABASE finpilot_db;
CREATE USER finpilot WITH PASSWORD 'finpilot_password';
GRANT ALL PRIVILEGES ON DATABASE finpilot_db TO finpilot;
GRANT ALL ON SCHEMA public TO finpilot;
```

```bash
# from backend/ with venv active
alembic upgrade head
python -m app.db.seed
```

### 4. Start backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/api/docs

### 5. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:3000

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection string |
| `JWT_SECRET` | Yes | Min 32 chars, keep secret |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default: 1440 (24h) |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |
| `AI_PROVIDER` | No | `demo` \| `groq` \| `openrouter` \| `ollama` |
| `GROQ_API_KEY` | No | From console.groq.com (free tier available) |
| `GROQ_MODEL` | No | Default: `llama-3.3-70b-versatile` |
| `OPENROUTER_API_KEY` | No | From openrouter.ai (free models available) |
| `AI_MODEL` | No | OpenRouter model ID |
| `DEMO_MODE` | No | `true` to force demo mode |
| `MAX_UPLOAD_SIZE_MB` | No | Default: 10 |

---

## Demo Credentials

After running `python -m app.db.seed`:

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@acmemfg.in` | `Admin@123` |
| Accountant | `accountant@acmemfg.in` | `Accountant@123` |
| Viewer | `viewer@acmemfg.in` | `Viewer@123` |

Demo company: **Acme Manufacturing Pvt. Ltd.** with 12 months of realistic financial data.

---

## AI Configuration

### Demo Mode (default — no API key needed)
```env
AI_PROVIDER=demo
DEMO_MODE=true
```

### Groq (fast, free tier — recommended)
```env
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.3-70b-versatile
DEMO_MODE=false
```

### OpenRouter (alternative, free models available)
```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
AI_MODEL=google/gemma-4-26b-a4b-it:free
DEMO_MODE=false
```

Switch providers at any time from **Settings → AI Config** in the app.

---

## Docker Setup

```bash
cp .env.example .env
docker compose up --build
```

Starts PostgreSQL (5432), FastAPI backend (8000), and React frontend (5173). Migrations and seed data run automatically on first start.

---

## Render Deployment

`render.yaml` defines all three services. On each deploy:
1. `alembic upgrade head` runs migrations automatically
2. `python -m app.db.seed` seeds demo data
3. CORS is configured for the live frontend URL

Health check: `GET /health`

---

## Database Schema (Key Tables)

| Table | Purpose |
|-------|---------|
| `companies` | Multi-tenant root — every table has `company_id` FK |
| `users` | Auth + RBAC (admin/accountant/viewer) |
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

---

## Running Tests

```bash
cd backend
# Create test database first
# psql -U postgres -c "CREATE DATABASE finpilot_test; GRANT ALL ON DATABASE finpilot_test TO finpilot;"
export TEST_DATABASE_URL=postgresql://finpilot:finpilot_password@localhost:5432/finpilot_test
pytest tests/ -v
```

Security invariants verified by tests:
- Company A cannot read Company B data
- VIEWER cannot create or modify financial records
- Only ADMIN can approve transactions
- AI tools cannot execute arbitrary database writes
- Connector token auth rejects invalid tokens

```bash
# Connector tests
cd tally-connector
pytest tests/ -v
```

---

## Project Structure

```
AI_Financial_Agents/
├── .env.example
├── docker-compose.yml
├── render.yaml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── core/                # Config, security
│   │   ├── auth/                # JWT dependencies
│   │   ├── api/v1/endpoints/    # All route handlers
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic + Tally sync service
│   │   ├── agents/              # AI agent orchestration
│   │   ├── tools/               # Controlled finance tools (read-only)
│   │   ├── analytics/           # Analytics queries
│   │   ├── reports/             # PDF generation (ReportLab)
│   │   ├── integrations/        # Tally abstraction layer
│   │   └── db/                  # Base, seed, types
│   ├── alembic/                 # Migrations
│   └── tests/                   # pytest (22 backend + Tally integration tests)
├── frontend/
│   └── src/
│       ├── api/                 # API client + endpoints
│       ├── auth/                # Auth context
│       ├── components/          # UI + layout + global Tally Activity Drawer
│       ├── pages/               # All page components
│       ├── types/               # TypeScript types
│       └── utils/               # Formatting helpers
└── tally-connector/
    ├── app.py                   # GUI desktop app (system tray, tkinter)
    ├── connector.py             # Headless terminal connector
    ├── tally_client.py          # TallyPrime XML API client
    ├── headless_sync.py         # Standalone sync script
    ├── start.bat                # One-click Python launcher
    ├── requirements.txt
    └── tests/                   # 29 connector unit tests
```

---

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/dashboard` | Dashboard | KPIs, charts, low-stock alerts |
| `/assistant` | AI Assistant | Multi-conversation finance chat |
| `/ai-create` | Create with AI | NL → entity extraction → create + Tally sync |
| `/transactions` | Transactions | Invoices + expenses list |
| `/vouchers` | Vouchers | Full CRUD for all TallyPrime voucher types |
| `/customers` | Customers | Full CRUD |
| `/vendors` | Vendors | Full CRUD |
| `/inventory` | Inventory | Product catalog + stock |
| `/uploads` | Bulk Uploads | CSV/PDF import |
| `/analytics` | Analytics | Date-range filtered charts |
| `/reports` | Reports | Generate + download PDFs |
| `/approvals` | Approvals | Approve/reject queue (ADMIN only) |
| `/audit-logs` | Audit Logs | Full action history |
| `/tally` | TallyPrime | Connector management + activity log |
| `/settings` | Settings | Company info + AI provider |

---

## Known Limitations

- Tally's XML API has limited delete support for master records (ledgers, stock items) — deletion is supported for vouchers only via REMOTEID
- Analytics date filter uses timezone-naive comparison
- PDF invoice AI extraction quality depends on the AI provider being used

## Future Scope

- GST return filing integration
- Bank reconciliation
- Email / WhatsApp invoice delivery
- Multi-currency support
- Budget vs actuals tracking
- Automated overdue reminders
- Individual management pages for Tally-only masters (ledgers, units, godowns)
- Real-time push notifications (currently polling-based)
- Mobile app (React Native)
