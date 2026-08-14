# FinPilot AI

**AI-Powered Finance Operations & Accounting Automation Platform**

FinPilot AI is a full-stack, production-grade web application for small and medium-sized businesses. It demonstrates how AI can safely interact with structured accounting data — with human approval required for every financial write.

---

## Screenshots

| Dashboard | AI Assistant | Customers | Analytics |
|-----------|-------------|-----------|-----------|
| Real KPIs + charts | Demo mode + live LLM | Full CRUD | Trend charts |

---

## Features

- **Dashboard** — Real-time KPIs (revenue, expenses, profit, receivables, payables) with 12-month charts
- **AI Finance Assistant** — Ask financial questions in natural language; AI uses controlled tools to query real data
- **AI Transaction Proposals** — Describe a transaction; AI extracts structure; human approves before commit
- **Transaction Management** — Invoices, expenses, payments with full status lifecycle
- **Approval Center** — All financial writes require explicit approval from ADMIN role
- **Customers & Vendors** — Full CRUD with revenue/outstanding tracking
- **Inventory** — Product management with low-stock alerts
- **Bulk Uploads** — CSV/XLSX import with validation, preview, and error reporting
- **PDF Reports** — P&L, Revenue, Expense, Receivables reports via ReportLab
- **Audit Logs** — Complete trail of every action
- **Multi-Provider AI** — OpenRouter, Groq, Ollama, or Demo mode (no API key needed)
- **RBAC** — Admin / Accountant / Viewer roles enforced at the API level
- **Company Isolation** — Multi-tenant; users only see their company's data
- **Tally Integration Layer** — Clean abstraction; PostgreSQL used by default

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL 17 |
| Auth | JWT (python-jose) + bcrypt password hashing |
| AI | OpenRouter / Groq / Ollama / Demo mode |
| PDF | ReportLab |
| File Processing | pandas, openpyxl |
| Testing | pytest, FastAPI TestClient |
| Deployment | Docker, Docker Compose, Render |

---

## Architecture

```
Browser (React)
    │ HTTPS / REST JSON
    ▼
FastAPI (Python)
    ├── JWT auth middleware
    ├── Company isolation filter (every query filtered by company_id)
    ├── Role-based authorization
    │
    ├── API endpoints
    │   ├── /api/auth/*
    │   ├── /api/dashboard/*
    │   ├── /api/assistant/*  ← Finance AI Agent
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
    │   └── /api/settings/*
    │
    ├── Finance AI Agent
    │   ├── FinanceTools (controlled DB access — READ only via typed tools)
    │   ├── OpenRouterAgent / GroqAgent / OllamaAgent / DemoAgent
    │   └── TransactionAgent (NL → structured proposal → human approval)
    │
    └── PostgreSQL (SQLAlchemy ORM + Alembic migrations)
```

### AI Safety Architecture

```
READ path:
  User question → FinanceAgent → Intent → FinanceTool (typed fn) → DB → Result → LLM explanation

WRITE path:
  User prompt → TransactionAgent → Structured proposal → Validation → Preview
               → Human clicks Approve → API endpoint → DB write → Audit log
```

**The LLM never directly writes to the database.**

---

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- PostgreSQL 17

### 1. Clone and configure

```bash
git clone <repo>
cd AI_Financial_Agents
cp .env.example .env
# Edit .env — set DATABASE_URL and optionally an AI API key
```

### 2. Backend (with venv)

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

Create the PostgreSQL database:
```sql
CREATE DATABASE finpilot_db;
CREATE USER finpilot WITH PASSWORD 'finpilot_password';
GRANT ALL PRIVILEGES ON DATABASE finpilot_db TO finpilot;
GRANT ALL ON SCHEMA public TO finpilot;
```

Run migrations and seed demo data:
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
| `AI_PROVIDER` | No | `demo` \| `openrouter` \| `groq` \| `ollama` |
| `AI_MODEL` | No | OpenRouter model ID |
| `OPENROUTER_API_KEY` | No | From openrouter.ai (free models available) |
| `GROQ_API_KEY` | No | From console.groq.com (free tier available) |
| `GROQ_MODEL` | No | Default: `llama-3.1-8b-instant` |
| `OLLAMA_BASE_URL` | No | Default: `http://localhost:11434` |
| `OLLAMA_MODEL` | No | Default: `llama3.2` |
| `DEMO_MODE` | No | `true` to force demo mode |
| `MAX_UPLOAD_SIZE_MB` | No | Default: 10 |
| `TALLY_ENABLED` | No | `false` by default |

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
The system uses rule-based pattern matching to answer common financial questions using real database data.

### OpenRouter (free models available)
```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
AI_MODEL=mistralai/mistral-7b-instruct:free
DEMO_MODE=false
```
Get a free key at https://openrouter.ai

### Groq (fast, free tier)
```env
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant
DEMO_MODE=false
```
Get a free key at https://console.groq.com

### Ollama (local, fully private)
```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
DEMO_MODE=false
```
Install: https://ollama.ai — then `ollama pull llama3.2`

You can switch providers at any time via the **Settings → AI Config** page in the app.

---

## Running Tests

```bash
cd backend
# Create a test database first
# psql -U postgres -c "CREATE DATABASE finpilot_test; GRANT ALL ON DATABASE finpilot_test TO finpilot;"
export TEST_DATABASE_URL=postgresql://finpilot:finpilot_password@localhost:5432/finpilot_test
pytest tests/ -v
```

Key security tests verified:
- Company A cannot read Company B data
- VIEWER cannot create/modify financial records
- Only ADMIN can approve transactions
- AI tools cannot execute arbitrary database writes

---

## Docker Setup

### Local development
```bash
cp .env.example .env
docker compose up --build
```

This starts:
- PostgreSQL on port 5432
- FastAPI backend on port 8000
- React frontend on port 5173

Migrations and seed data run automatically on first start.

### Production build test
```bash
# Backend
cd backend && docker build -t finpilot-backend .

# Frontend
cd frontend && docker build -t finpilot-frontend .
```

---

## Render Deployment

1. Create a PostgreSQL database on Render (free tier available)
2. Create a Web Service for the backend:
   - Build: `pip install -r requirements.txt`
   - Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Set environment variables (DATABASE_URL, JWT_SECRET, etc.)
3. Create a Static Site for the frontend:
   - Build: `npm install && npm run build`
   - Publish: `dist`
   - Set `VITE_API_URL` to your backend URL

Health check endpoint: `GET /health`

---

## Tally Integration

FinPilot AI uses a `FinanceDataProvider` abstraction:

```
App → FinanceDataProvider (abstract interface)
         ├── PostgresFinanceProvider (default — always works)
         └── TallyFinanceProvider (optional — requires TallyPrime)
```

To enable Tally:
1. Enable XML bridge in TallyPrime: Gateway → F12 → Enable ODBC
2. Set in `.env`:
   ```env
   TALLY_ENABLED=true
   TALLY_HOST=localhost
   TALLY_PORT=9000
   ```
3. The app will communicate with Tally via its HTTP XML interface

**Important:** The deployed application works fully without TallyPrime. Tally is an optional data source, not a dependency.

---

## Security Model

- Passwords hashed with bcrypt (never stored plain)
- JWT tokens — short-lived, secret-keyed
- Every API endpoint verifies company ownership before returning data
- Role-based authorization enforced at the API level (not just frontend)
- AI tools are read-only and strongly typed — no arbitrary SQL
- All financial writes require human approval
- Audit log records every significant action with user, timestamp, IP

---

## API Documentation

Interactive docs available at `http://localhost:8000/api/docs` (Swagger UI).

Key endpoints:
- `POST /api/auth/signup` — Create account + company
- `POST /api/auth/login` — Login
- `GET /api/dashboard/overview` — Financial summary
- `POST /api/assistant/conversations/{id}/messages` — Ask AI
- `POST /api/assistant/propose-transaction` — AI transaction proposal
- `POST /api/approvals/{id}/approve` — Approve a transaction (ADMIN only)
- `POST /api/reports/generate` — Generate PDF report
- `POST /api/uploads/csv` — Upload CSV data
- `GET /health` — Health check

---

## Project Structure

```
AI_Financial_Agents/
├── .env.example
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry
│   │   ├── core/                # Config, security
│   │   ├── auth/                # JWT dependencies
│   │   ├── api/v1/endpoints/    # All route handlers
│   │   ├── models/              # SQLAlchemy models
│   │   ├── schemas/             # Pydantic schemas
│   │   ├── services/            # Business logic
│   │   ├── agents/              # AI agent orchestration
│   │   ├── tools/               # Controlled finance tools
│   │   ├── analytics/           # Analytics queries
│   │   ├── reports/             # PDF generation
│   │   ├── integrations/        # Tally abstraction
│   │   └── db/                  # Base, seed, types
│   ├── alembic/                 # Migrations
│   ├── tests/                   # pytest tests
│   ├── requirements.txt
│   ├── setup_venv.ps1           # Windows venv setup
│   └── setup_venv.sh            # Linux/macOS venv setup
└── frontend/
    └── src/
        ├── api/                 # API client + endpoints
        ├── auth/                # Auth context
        ├── components/          # UI + layout components
        ├── pages/               # All page components
        ├── types/               # TypeScript types
        └── utils/               # Formatting helpers
```

---

## Known Limitations

- PDF invoice extraction requires PyMuPDF — works but AI extraction quality depends on provider
- Tally sync is documented but not fully implemented (abstraction layer is in place)
- Analytics date filter with `Last 30 Days` shows data based on timezone-naive comparison
- Frontend reports page uses `monthly_summary` type which maps to P&L on the backend

---

## Future Improvements

- GST return filing integration
- Bank reconciliation
- Email/WhatsApp invoice delivery
- Multi-currency support
- Budget vs actuals tracking
- Automated overdue reminders
- More Tally entity sync (stock items, ledgers)
- Mobile app (React Native)
