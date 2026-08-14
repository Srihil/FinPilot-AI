"""
FinPilot Tally Connector
========================
Lightweight Python process that runs on the same Windows PC as TallyPrime.

Responsibilities:
  1. Pair with FinPilot cloud using a user-supplied pairing code.
  2. Periodically send heartbeats so the cloud knows the connector is alive.
  3. Poll the cloud for pending integration jobs.
  4. Execute each job against TallyPrime via HTTP/XML.
  5. Post results back to the cloud.
  6. Reconnect automatically after network failures.

Security model:
  - Never exposes TallyPrime to the internet.
  - Only outbound HTTPS requests to FinPilot cloud.
  - Token is stored locally in .env; never logged.
  - All Tally XML is constructed by this process (not by the cloud).
"""
import json
import logging
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

from config import config
from tally_client import TallyClient, TallyError

logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("connector")

ENV_FILE = Path(__file__).parent / ".env"

# ─── Cloud API helpers ────────────────────────────────────────────────────────

def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.CONNECTOR_TOKEN}",
        "Content-Type": "application/json",
    }


def _api(path: str) -> str:
    base = config.FINPILOT_API_URL.rstrip("/")
    return f"{base}{path}"


def send_heartbeat(tally: TallyClient) -> None:
    reachable = tally.is_reachable()
    company = None
    if reachable:
        company_info = tally.get_active_company()
        if company_info:
            company = company_info.get("name")

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
        data = resp.json()
        return data.get("jobs", [])


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


# ─── Job execution router ─────────────────────────────────────────────────────

# Whitelist of allowed operations — cloud cannot inject arbitrary operations
ALLOWED_OPERATIONS = {
    "READ_COMPANIES",
    "READ_LEDGERS",
    "READ_VOUCHERS",
    "READ_SALES",
    "READ_PURCHASES",
    "READ_RECEIVABLES",
    "READ_PAYABLES",
    "READ_STOCK_ITEMS",
    "CREATE_SALES_VOUCHER",
    "CREATE_PURCHASE_VOUCHER",
    "CREATE_RECEIPT_VOUCHER",
    "CREATE_PAYMENT_VOUCHER",
    "CREATE_LEDGER",
    "CREATE_STOCK_ITEM",
    "SYNC_FULL",
    "SYNC_PARTIAL",
}


def execute_job(tally: TallyClient, job: dict) -> tuple[Optional[dict], Optional[str]]:
    """
    Returns (result_dict, error_message).
    error_message is None on success.
    """
    op = job.get("operation", "")
    payload = job.get("payload") or {}
    job_id = job.get("id", "?")

    if op not in ALLOWED_OPERATIONS:
        return None, f"Operation not allowed: {op}"

    logger.info("Executing job %s: %s", job_id, op)

    try:
        if op == "READ_COMPANIES":
            company = tally.get_active_company()
            return {"company": company}, None

        if op == "READ_LEDGERS":
            ledgers = tally.get_ledgers()
            return {"ledgers": ledgers, "count": len(ledgers)}, None

        if op == "READ_VOUCHERS":
            vouchers = tally.get_vouchers(
                from_date=payload.get("from_date", ""),
                to_date=payload.get("to_date", ""),
            )
            return {"vouchers": vouchers, "count": len(vouchers)}, None

        if op == "READ_SALES":
            sales = tally.get_sales(
                from_date=payload.get("from_date", ""),
                to_date=payload.get("to_date", ""),
            )
            return {"sales": sales, "count": len(sales)}, None

        if op == "READ_PURCHASES":
            purchases = tally.get_purchases(
                from_date=payload.get("from_date", ""),
                to_date=payload.get("to_date", ""),
            )
            return {"purchases": purchases, "count": len(purchases)}, None

        if op == "READ_RECEIVABLES":
            receivables = tally.get_receivables()
            return {"receivables": receivables, "count": len(receivables)}, None

        if op == "READ_PAYABLES":
            payables = tally.get_payables()
            return {"payables": payables, "count": len(payables)}, None

        if op == "READ_STOCK_ITEMS":
            items = tally.get_stock_items()
            return {"stock_items": items, "count": len(items)}, None

        if op == "CREATE_SALES_VOUCHER":
            result = tally.create_sales_voucher(payload)
            return result, None

        if op == "CREATE_PURCHASE_VOUCHER":
            result = tally.create_purchase_voucher(payload)
            return result, None

        if op in ("CREATE_RECEIPT_VOUCHER", "CREATE_PAYMENT_VOUCHER"):
            return None, f"{op} not implemented in this connector version"

        if op == "CREATE_LEDGER":
            result = tally.create_ledger(payload)
            return result, None

        if op == "CREATE_STOCK_ITEM":
            return None, "CREATE_STOCK_ITEM not implemented in this connector version"

        if op in ("SYNC_FULL", "SYNC_PARTIAL"):
            ledgers = tally.get_ledgers()
            stock = tally.get_stock_items()
            return {
                "synced": True,
                "ledger_count": len(ledgers),
                "stock_item_count": len(stock),
            }, None

    except TallyError as e:
        return None, str(e)
    except Exception as e:
        logger.exception("Unexpected error in job %s", job_id)
        return None, f"Internal error: {type(e).__name__}: {e}"

    return None, f"Unhandled operation: {op}"


# ─── Pairing flow ─────────────────────────────────────────────────────────────

def pair(pairing_code: str, connector_name: str = "FinPilot Connector") -> str:
    """Register with FinPilot cloud using the user-supplied pairing code.
    Returns the connector token and saves it to .env.
    """
    import socket
    device_name = socket.gethostname()
    payload = {
        "pairing_code": pairing_code.strip().upper(),
        "connector_name": connector_name,
        "device_name": device_name,
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(
            _api("/api/tally/connector/register"),
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code == 400:
            data = resp.json()
            raise ValueError(data.get("detail", "Invalid pairing code"))
        resp.raise_for_status()
        data = resp.json()

    token = data["token"]
    poll_interval = data.get("poll_interval_seconds", 10)

    # Persist token to .env
    env_content = ENV_FILE.read_text() if ENV_FILE.exists() else ""
    lines = [l for l in env_content.splitlines() if not l.startswith("CONNECTOR_TOKEN=")]
    lines.append(f"CONNECTOR_TOKEN={token}")
    ENV_FILE.write_text("\n".join(lines) + "\n")

    logger.info("Paired successfully! Connector ID: %s", data["connector_id"])
    logger.info("Poll interval: %ds", poll_interval)
    return token


# ─── Main loop ────────────────────────────────────────────────────────────────

def run():
    if not config.CONNECTOR_TOKEN:
        print("\n" + "=" * 60)
        print("  FinPilot Tally Connector — First-Time Setup")
        print("=" * 60)
        print(f"\n  Backend URL: {config.FINPILOT_API_URL}")
        print("\n  No connector token found.")
        print("  1. Go to FinPilot → Settings → TallyPrime → Connect")
        print("  2. Copy the pairing code shown")
        print("  3. Enter it below\n")
        code = input("  Enter pairing code (e.g. ABCD-EFGH): ").strip()
        if not code:
            print("  No code entered. Exiting.")
            sys.exit(1)
        try:
            token = pair(code)
            config.CONNECTOR_TOKEN = token
            print("\n  ✓ Paired successfully! Token saved to .env")
        except ValueError as e:
            print(f"\n  ✗ Pairing failed: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"\n  ✗ Network error: {e}")
            sys.exit(1)

    tally = TallyClient(host=config.TALLY_HOST, port=config.TALLY_PORT)

    print("\n" + "=" * 60)
    print("  FinPilot Tally Connector — Running")
    print("=" * 60)
    print(f"  Backend: {config.FINPILOT_API_URL}")
    print(f"  Tally:   {config.TALLY_HOST}:{config.TALLY_PORT}")
    print(f"  Poll:    every {config.POLL_INTERVAL_SECONDS}s")
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
                    logger.error("Connector token rejected (401). Re-pair the connector.")
                    sys.exit(1)
                raise

            if jobs:
                logger.info("Got %d job(s)", len(jobs))
                for job in jobs:
                    job_id = job["id"]
                    result, error = execute_job(tally, job)
                    status = "SUCCESS" if error is None else "FAILED"
                    try:
                        post_result(job_id, status, result, error)
                        logger.info("Job %s → %s", job_id, status)
                    except Exception as e:
                        logger.warning("Failed to post result for job %s: %s", job_id, e)

            time.sleep(config.POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n\n  Connector stopped.")
            sys.exit(0)
        except Exception as e:
            logger.error("Error in main loop: %s — retrying in 30s", e)
            time.sleep(30)


if __name__ == "__main__":
    run()
