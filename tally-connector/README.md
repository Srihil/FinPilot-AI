# FinPilot Tally Connector

Lightweight Python process that runs on the **same Windows PC as TallyPrime** and bridges FinPilot cloud with your local Tally installation.

## Architecture

```
Browser
  │
  ▼
FinPilot Frontend (Render)
  │
  ▼
FinPilot Backend API (Render) ◄──── HTTPS (outbound from connector)
  │                                         │
  │  Job Queue (PostgreSQL)                 │
  │                                         │
  ▼                                         │
FinPilot Tally Connector (this) ────────────┘
  │
  │  HTTP/XML (localhost only)
  ▼
TallyPrime HTTP Server (localhost:9000)
```

**TallyPrime is NEVER exposed to the internet.** The connector only makes outbound HTTPS requests.

---

## Prerequisites

- Windows 10/11
- Python 3.10+ (download from [python.org](https://python.org))
- TallyPrime 2.x or higher
- An active FinPilot account with Admin role

---

## TallyPrime Setup

Enable the HTTP server in TallyPrime:

1. Open TallyPrime and load your company
2. Press **F12** → **Configure** → **Connectivity**
3. Set **Enable ODBC Server** to **Yes**
4. Set **Port** to **9000**
5. Press **Enter** to save
6. Verify by visiting `http://localhost:9000` in a browser — you should see a response

---

## Connector Setup

### Option A — Double-click launcher (recommended)

1. Download / copy this `tally-connector` folder to your PC
2. Double-click **`start.bat`**
3. The script creates a virtual environment and installs dependencies automatically

### Option B — Manual setup

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
:: edit .env — set FINPILOT_API_URL
python connector.py
```

---

## Pairing (First Run)

1. In FinPilot web app: **Settings → TallyPrime → Connect TallyPrime**
2. Copy the 8-character pairing code (valid for 10 minutes)
3. The connector will prompt you to enter this code on first run
4. After pairing, the connector token is saved in `.env` and used automatically on subsequent runs

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `FINPILOT_API_URL` | — | **Required.** Your FinPilot backend URL on Render |
| `CONNECTOR_TOKEN` | — | Set automatically after pairing. Do not share. |
| `TALLY_HOST` | `localhost` | TallyPrime host (almost always localhost) |
| `TALLY_PORT` | `9000` | TallyPrime HTTP server port |
| `POLL_INTERVAL_SECONDS` | `10` | How often to poll cloud for new jobs |
| `HEARTBEAT_INTERVAL_SECONDS` | `30` | How often to send heartbeat |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Cannot connect to TallyPrime on localhost:9000" | Enable HTTP server in TallyPrime (F12 → Configure → Connectivity) and open a company |
| "Connector token rejected (401)" | Token revoked in FinPilot. Re-pair by deleting `CONNECTOR_TOKEN` from `.env` and running again |
| "Invalid or expired pairing code" | Code expired (10 min). Generate a new one in FinPilot |
| Connector shows offline in FinPilot | Heartbeat not received — check internet connection and that the connector process is running |
| "TallyPrime is offline" in FinPilot | Tally not running, no company loaded, or HTTP server disabled |

---

## Security Notes

- The connector token is equivalent to a password — keep `.env` private
- The connector **never** stores TallyPrime passwords
- All communication to FinPilot cloud is outbound HTTPS — no inbound ports needed
- All Tally XML is constructed locally by this connector — the cloud never sends raw XML

---

## Supported Operations

### Read (automatic during sync)
- List of companies/active company
- Ledgers with closing balances
- Vouchers (all types) with date range
- Sales vouchers
- Purchase vouchers
- Outstanding receivables
- Outstanding payables
- Stock items with closing balances

### Write (requires human approval in FinPilot first)
- Create Sales voucher
- Create Purchase voucher
- Create Ledger (party master)
