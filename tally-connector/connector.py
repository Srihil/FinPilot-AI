"""
FinPilot Tally Connector
========================
Runs on the same Windows PC as TallyPrime.
Bridges FinPilot cloud with local TallyPrime via secure HTTPS polling.
"""
import sys
import time
import traceback
from pathlib import Path
from typing import Optional


# ─── Keep window open on any crash (must be before all other imports) ─────────

def _fatal(msg: str) -> None:
    print("\n" + "=" * 60)
    print("  FinPilot Connector — Error")
    print("=" * 60)
    print(f"\n{msg}")
    print("\n  Common fixes:")
    print("  1. Run as Administrator (right-click → Run as administrator)")
    print("  2. Allow the app in Windows Defender / Antivirus")
    print("  3. Delete the .env file next to this .exe and re-pair")
    print("  4. Make sure TallyPrime is open with a company loaded")
    print()
    input("  Press Enter to close...")
    sys.exit(1)


try:
    import json
    import logging
    import httpx
    from config import config, BASE_DIR
    from tally_client import TallyClient, TallyError
except Exception as _import_err:
    _fatal(f"Startup failed (import error):\n\n  {type(_import_err).__name__}: {_import_err}\n\n{traceback.format_exc()}")


# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("connector")

ENV_FILE = BASE_DIR / ".env"

MAX_RETRY = 3


# ─── Cloud API helpers ────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.CONNECTOR_TOKEN}",
        "Content-Type": "application/json",
    }


def _api(path: str) -> str:
    return config.FINPILOT_API_URL.rstrip("/") + path


def send_heartbeat(tally: TallyClient) -> None:
    reachable = tally.is_reachable()
    company = None
    if reachable:
        info = tally.get_active_company()
        if info:
            company = info.get("name")

    payload = {
        "tally_reachable": reachable,
        "tally_company_name": company,
        "tally_host": config.TALLY_HOST,
        "tally_port": config.TALLY_PORT,
    }
    with httpx.Client(timeout=10) as client:
        client.post(_api("/api/tally/connector/heartbeat"), json=payload, headers=_headers())
    status = f"TallyPrime: {'Online' if reachable else 'Offline'}"
    if company:
        status += f" | Company: {company}"
    logger.info("Heartbeat sent — %s", status)


def poll_jobs() -> list[dict]:
    with httpx.Client(timeout=15) as client:
        resp = client.get(_api("/api/tally/connector/jobs"), headers=_headers())
        resp.raise_for_status()
        return resp.json().get("jobs", [])


def post_result(job_id: str, status: str, result: Optional[dict], error: Optional[str]) -> None:
    payload: dict = {"status": status}
    if result is not None:
        payload["result"] = result
    if error is not None:
        payload["error_message"] = error
    with httpx.Client(timeout=15) as client:
        resp = client.post(
            _api(f"/api/tally/connector/jobs/{job_id}/result"),
            json=payload,
            headers=_headers(),
        )
        resp.raise_for_status()


# ─── Job execution ────────────────────────────────────────────────────────────

ALLOWED_OPERATIONS = {
    # Read
    "READ_COMPANIES", "READ_LEDGERS", "READ_VOUCHERS", "READ_SALES",
    "READ_PURCHASES", "READ_RECEIVABLES", "READ_PAYABLES", "READ_STOCK_ITEMS",
    # Accounting masters
    "CREATE_LEDGER", "CREATE_GROUP",
    # Inventory masters
    "CREATE_STOCK_ITEM", "CREATE_STOCK_GROUP", "CREATE_UNIT", "CREATE_GODOWN",
    # Voucher type
    "CREATE_VOUCHER_TYPE",
    # Delete operations
    "DELETE_LEDGER", "DELETE_STOCK_ITEM", "DELETE_STOCK_GROUP", "DELETE_UNIT", "DELETE_GODOWN",
    # Vouchers
    "CREATE_SALES_VOUCHER", "CREATE_PURCHASE_VOUCHER",
    "CREATE_RECEIPT_VOUCHER", "CREATE_PAYMENT_VOUCHER",
    "CREATE_JOURNAL_VOUCHER", "CREATE_CREDIT_NOTE", "CREATE_DEBIT_NOTE",
    "CREATE_CONTRA_VOUCHER",
    # Voucher cancel (Tally-confirmed-first delete)
    "CANCEL_VOUCHER",
    # Sync
    "SYNC_FULL", "SYNC_PARTIAL",
}


def execute_job(tally: TallyClient, job: dict) -> tuple[Optional[dict], Optional[str]]:
    op = job.get("operation", "")
    payload = job.get("payload") or {}
    job_id = job.get("id", "?")

    if op not in ALLOWED_OPERATIONS:
        return None, f"Operation not allowed: {op}"

    logger.info("Executing job %s: %s", job_id, op)

    try:
        if op == "READ_COMPANIES":
            return {"company": tally.get_active_company()}, None
        if op == "READ_LEDGERS":
            items = tally.get_ledgers()
            return {"ledgers": items, "count": len(items)}, None
        if op == "READ_VOUCHERS":
            items = tally.get_vouchers(payload.get("from_date", ""), payload.get("to_date", ""))
            return {"vouchers": items, "count": len(items)}, None
        if op == "READ_SALES":
            items = tally.get_sales(payload.get("from_date", ""), payload.get("to_date", ""))
            return {"sales": items, "count": len(items)}, None
        if op == "READ_PURCHASES":
            items = tally.get_purchases(payload.get("from_date", ""), payload.get("to_date", ""))
            return {"purchases": items, "count": len(items)}, None
        if op == "READ_RECEIVABLES":
            items = tally.get_receivables()
            return {"receivables": items, "count": len(items)}, None
        if op == "READ_PAYABLES":
            items = tally.get_payables()
            return {"payables": items, "count": len(items)}, None
        if op == "READ_STOCK_ITEMS":
            items = tally.get_stock_items()
            return {"stock_items": items, "count": len(items)}, None
        # Accounting masters
        if op == "CREATE_LEDGER":
            return tally.create_ledger(payload), None
        if op == "CREATE_GROUP":
            return tally.create_group(payload), None
        # Inventory masters
        if op == "CREATE_STOCK_ITEM":
            return tally.create_stock_item(payload), None
        if op == "CREATE_STOCK_GROUP":
            return tally.create_stock_group(payload), None
        if op == "CREATE_UNIT":
            return tally.create_unit(payload), None
        if op == "CREATE_GODOWN":
            return tally.create_godown(payload), None
        if op == "CREATE_VOUCHER_TYPE":
            return tally.create_voucher_type(payload), None
        # Vouchers
        if op == "CREATE_SALES_VOUCHER":
            return tally.create_sales_voucher(payload), None
        if op == "CREATE_PURCHASE_VOUCHER":
            return tally.create_purchase_voucher(payload), None
        if op == "CREATE_RECEIPT_VOUCHER":
            return tally.create_receipt_voucher(payload), None
        if op == "CREATE_PAYMENT_VOUCHER":
            return tally.create_payment_voucher(payload), None
        if op == "CREATE_JOURNAL_VOUCHER":
            return tally.create_journal_voucher(payload), None
        if op == "CREATE_CREDIT_NOTE":
            return tally.create_credit_note(payload), None
        if op == "CREATE_DEBIT_NOTE":
            return tally.create_debit_note(payload), None
        if op == "CREATE_CONTRA_VOUCHER":
            return tally.create_contra_voucher(payload), None
        if op == "DELETE_LEDGER":
            return tally.delete_ledger(payload), None
        if op == "DELETE_STOCK_GROUP":
            return tally.delete_stock_group(payload), None
        if op == "DELETE_UNIT":
            return tally.delete_unit(payload), None
        if op == "DELETE_GODOWN":
            return tally.delete_godown(payload), None
        if op == "DELETE_STOCK_ITEM":
            return tally.delete_stock_item(payload), None
        if op == "CANCEL_VOUCHER":
            return tally.cancel_voucher(payload), None
        if op in ("SYNC_FULL", "SYNC_PARTIAL"):
            ledgers      = tally.get_ledgers()
            vouchers     = tally.get_vouchers()
            stock        = tally.get_stock_items()
            godowns      = tally.get_godowns()
            stock_groups = tally.get_stock_groups()
            units        = tally.get_units()
            groups        = tally.get_groups()
            voucher_types = tally.get_voucher_types()
            return {
                "synced": True,
                "ledgers":       ledgers,
                "vouchers":      vouchers,
                "stock_items":   stock,
                "godowns":       godowns,
                "stock_groups":  stock_groups,
                "units":         units,
                "groups":        groups,
                "voucher_types": voucher_types,
                "ledger_count":       len(ledgers),
                "voucher_count":      len(vouchers),
                "stock_item_count":   len(stock),
                "godown_count":       len(godowns),
                "stock_group_count":  len(stock_groups),
                "unit_count":         len(units),
                "group_count":        len(groups),
                "voucher_type_count": len(voucher_types),
            }, None
    except TallyError as e:
        return None, str(e)
    except Exception as e:
        logger.exception("Unexpected error in job %s", job_id)
        return None, f"Internal error: {type(e).__name__}: {e}"

    return None, f"Unhandled operation: {op}"


# ─── Env helpers ──────────────────────────────────────────────────────────────

def _save_env_value(key: str, value: str) -> None:
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = [l for l in content.splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─── Pairing flow ─────────────────────────────────────────────────────────────

def _setup_backend_url() -> None:
    pass  # URL is hardcoded in config — nothing to ask


def pair(pairing_code: str) -> str:
    import socket
    payload = {
        "pairing_code": pairing_code.strip().upper(),
        "connector_name": "FinPilot Connector",
        "device_name": socket.gethostname(),
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            _api("/api/tally/connector/register"),
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 400:
            raise ValueError(resp.json().get("detail", "Invalid pairing code"))
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    _save_env_value("CONNECTOR_TOKEN", token)
    logger.info("Paired! Connector ID: %s", data["connector_id"])
    return token


# ─── Main loop ────────────────────────────────────────────────────────────────

def run() -> None:
    if not config.CONNECTOR_TOKEN:
        print("\n" + "=" * 60)
        print("  FinPilot Tally Connector — First-Time Setup")
        print("=" * 60)

        print(f"\n  Connecting to: {config.FINPILOT_API_URL}")
        print("\n  1. Open FinPilot: https://finpilot-frontend-vbdf.onrender.com/tally")
        print("  2. Click 'Connect TallyPrime'")
        print("  3. Copy the pairing code shown\n")
        code = input("  Enter pairing code (e.g. ABCD-EFGHI): ").strip()
        if not code:
            _fatal("No pairing code entered.")
        try:
            token = pair(code)
            config.CONNECTOR_TOKEN = token
            print("\n  ✓ Paired successfully! Token saved.")
        except ValueError as e:
            _fatal(f"Pairing failed: {e}")
        except Exception as e:
            _fatal(f"Network error during pairing:\n  {e}\n\nIs the backend URL correct?")

    tally = TallyClient(host=config.TALLY_HOST, port=config.TALLY_PORT)

    print("\n" + "=" * 60)
    print("  FinPilot Tally Connector — Running")
    print("=" * 60)
    print(f"  Backend : {config.FINPILOT_API_URL}")
    print(f"  Tally   : {config.TALLY_HOST}:{config.TALLY_PORT}")
    print(f"  Poll    : every {config.POLL_INTERVAL_SECONDS}s")
    print("  Press Ctrl+C to stop\n")

    last_heartbeat = 0.0

    while True:
        try:
            now = time.time()
            if now - last_heartbeat >= config.HEARTBEAT_INTERVAL_SECONDS:
                try:
                    send_heartbeat(tally)
                    last_heartbeat = now
                except Exception as e:
                    logger.warning("Heartbeat failed: %s", e)

            try:
                jobs = poll_jobs()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    _fatal("Connector token rejected (401).\n\n  The connector has been revoked or the token is invalid.\n  Delete the .env file next to this .exe and re-pair.")
                raise

            if jobs:
                logger.info("Got %d job(s)", len(jobs))
                for job in jobs:
                    job_id = job["id"]
                    result, error = execute_job(tally, job)
                    try:
                        post_result(job_id, "SUCCESS" if error is None else "FAILED", result, error)
                        logger.info("Job %s → %s", job_id, "SUCCESS" if error is None else "FAILED")
                    except Exception as e:
                        logger.warning("Failed to post result for job %s: %s", job_id, e)

            time.sleep(config.POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n\n  Connector stopped.")
            sys.exit(0)
        except Exception as e:
            logger.error("Error in main loop: %s — retrying in 30s", e)
            time.sleep(30)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        run()
    except SystemExit:
        raise
    except Exception as e:
        _fatal(f"Unexpected crash:\n\n{traceback.format_exc()}")
