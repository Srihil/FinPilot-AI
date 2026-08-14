"""
FinPilot Headless Sync
======================
Pairs the connector with the live backend and runs one full sync — no GUI.

Usage:
    python headless_sync.py --email EMAIL --password PASSWORD [--api-url URL]

Defaults:
    --api-url  https://finpilot-backend-w1im.onrender.com
"""
import argparse
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("fp-headless")

try:
    import httpx
    from config import config, BASE_DIR
    from tally_client import TallyClient, TallyError
except Exception as e:
    print(f"Import error: {e}")
    print("Make sure you run this from inside the tally-connector/ directory with deps installed.")
    sys.exit(1)

ENV_FILE = BASE_DIR / ".env"

ALLOWED_OPS = {
    "SYNC_FULL", "SYNC_PARTIAL", "READ_LEDGERS", "READ_VOUCHERS",
    "READ_COMPANIES", "READ_SALES", "READ_PURCHASES",
    "READ_RECEIVABLES", "READ_PAYABLES", "READ_STOCK_ITEMS",
    "CREATE_SALES_VOUCHER", "CREATE_PURCHASE_VOUCHER",
    "CREATE_RECEIPT_VOUCHER", "CREATE_PAYMENT_VOUCHER",
    "CREATE_LEDGER", "CREATE_STOCK_ITEM",
}


def _save_env(key: str, value: str) -> None:
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = [l for l in content.splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def login(api_url: str, email: str, password: str) -> str:
    log.info(f"Logging in as {email} ...")
    with httpx.Client(timeout=60) as c:
        r = c.post(f"{api_url}/api/auth/login", json={"email": email, "password": password})
        if r.status_code == 401:
            log.error("Login failed — wrong email or password.")
            sys.exit(1)
        r.raise_for_status()
        token = r.json().get("access_token") or r.json().get("token")
        if not token:
            log.error(f"Unexpected login response: {r.text[:200]}")
            sys.exit(1)
        log.info("Login OK.")
        return token


def generate_pairing_code(api_url: str, jwt: str) -> str:
    log.info("Generating pairing code ...")
    with httpx.Client(timeout=30) as c:
        r = c.post(
            f"{api_url}/api/tally/pairing/generate",
            headers={"Authorization": f"Bearer {jwt}"},
        )
        r.raise_for_status()
        code = r.json()["code"]
        log.info(f"Pairing code: {code}  (expires in {r.json()['expires_in_minutes']} min)")
        return code


def register_connector(api_url: str, code: str) -> str:
    import socket
    log.info("Registering connector with pairing code ...")
    with httpx.Client(timeout=70) as c:
        r = c.post(
            f"{api_url}/api/tally/connector/register",
            json={
                "pairing_code": code,
                "connector_name": "FinPilot Headless Connector",
                "device_name": socket.gethostname(),
            },
        )
        if r.status_code == 400:
            log.error(f"Pairing failed: {r.json().get('detail')}")
            sys.exit(1)
        r.raise_for_status()
        token = r.json()["token"]
        log.info("Connector registered.")
        return token


def execute_job(tally: TallyClient, job: dict):
    op = job.get("operation", "")
    pl = job.get("payload") or {}
    if op not in ALLOWED_OPS:
        return None, f"Operation not allowed: {op}"
    try:
        if op == "READ_COMPANIES":
            return {"company": tally.get_active_company()}, None
        if op == "READ_LEDGERS":
            d = tally.get_ledgers()
            return {"ledgers": d, "count": len(d)}, None
        if op == "READ_VOUCHERS":
            d = tally.get_vouchers(pl.get("from_date", ""), pl.get("to_date", ""))
            return {"vouchers": d, "count": len(d)}, None
        if op in ("SYNC_FULL", "SYNC_PARTIAL"):
            log.info("Fetching ledgers from TallyPrime ...")
            ledgers = tally.get_ledgers()
            log.info(f"  Got {len(ledgers)} ledgers")
            log.info("Fetching vouchers from TallyPrime (Day Book) ...")
            vouchers = tally.get_vouchers()
            log.info(f"  Got {len(vouchers)} vouchers")
            log.info("Fetching stock items ...")
            stock = tally.get_stock_items()
            log.info(f"  Got {len(stock)} stock items")
            return {
                "synced": True,
                "ledgers": ledgers,
                "vouchers": vouchers,
                "stock_items": stock,
                "ledger_count": len(ledgers),
                "voucher_count": len(vouchers),
                "stock_item_count": len(stock),
            }, None
        return None, f"Not implemented: {op}"
    except TallyError as e:
        return None, str(e)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def run_sync(api_url: str, connector_token: str, tally: TallyClient, max_wait: int = 120):
    headers = {
        "Authorization": f"Bearer {connector_token}",
        "Content-Type": "application/json",
    }

    def _url(path):
        return api_url.rstrip("/") + path

    log.info("Polling for pending jobs ...")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        with httpx.Client(timeout=15) as c:
            r = c.get(_url("/api/tally/connector/jobs"), headers=headers)
            r.raise_for_status()
            jobs = r.json().get("jobs", [])

        if jobs:
            log.info(f"Found {len(jobs)} job(s). Processing ...")
            for job in jobs:
                log.info(f"  Job {job['id'][:8]}…  operation={job['operation']}")
                result, error = execute_job(tally, job)
                payload = {"status": "SUCCESS" if error is None else "FAILED"}
                if result:
                    payload["result"] = result
                if error:
                    payload["error_message"] = error
                    log.error(f"  Job failed: {error}")

                with httpx.Client(timeout=30) as c:
                    c.post(
                        _url(f"/api/tally/connector/jobs/{job['id']}/result"),
                        json=payload,
                        headers=headers,
                    )

                if error is None:
                    stats = (result or {}).get
                    log.info(
                        f"  ✓ Job complete — "
                        f"ledgers={result.get('ledger_count', 0)}  "
                        f"vouchers={result.get('voucher_count', 0)}  "
                        f"stock={result.get('stock_item_count', 0)}"
                    )
            log.info("All jobs processed. Sync done — check your live website!")
            return

        time.sleep(3)

    log.warning("No pending sync job found within the wait window.")
    log.info("Go to the TallyPrime page on your live website and click 'Sync Now', then re-run this script.")


def main():
    ap = argparse.ArgumentParser(description="FinPilot headless TallyPrime sync")
    ap.add_argument("--api-url", default="https://finpilot-backend-w1im.onrender.com")
    ap.add_argument("--email",    default="admin@acmemfg.in",
                    help="Your FinPilot account email (default: demo account)")
    ap.add_argument("--password", default="Admin@123",
                    help="Your FinPilot account password (default: demo account)")
    args = ap.parse_args()

    api_url = args.api_url.rstrip("/")
    log.info(f"Target backend: {api_url}")

    # Step 1: login
    jwt = login(api_url, args.email, args.password)

    # Step 2: generate pairing code
    code = generate_pairing_code(api_url, jwt)

    # Step 3: register connector → get token
    connector_token = register_connector(api_url, code)
    _save_env("CONNECTOR_TOKEN", connector_token)
    log.info("Connector token saved to .env")

    headers_conn = {
        "Authorization": f"Bearer {connector_token}",
        "Content-Type": "application/json",
    }
    headers_user = {"Authorization": f"Bearer {jwt}"}

    # Step 4: connect to TallyPrime and send heartbeat FIRST
    # (backend checks last_heartbeat to decide if connector is "online" before accepting sync)
    tally = TallyClient(host=config.TALLY_HOST, port=config.TALLY_PORT)
    reachable = tally.is_reachable()
    company = None
    if reachable:
        info = tally.get_active_company()
        company = (info or {}).get("name", "")
    log.info(f"TallyPrime reachable={reachable}  company={company!r}")

    if not reachable:
        log.error(
            "TallyPrime is NOT reachable on localhost:9000.\n"
            "  → Open TallyPrime, open a company, enable HTTP server\n"
            "    (F12 → Configure → Connectivity → port 9000), then re-run."
        )
        sys.exit(1)

    log.info("Sending heartbeat so backend marks connector online ...")
    with httpx.Client(timeout=15) as c:
        c.post(f"{api_url}/api/tally/connector/heartbeat", json={
            "tally_reachable": reachable,
            "tally_company_name": company,
            "tally_host": config.TALLY_HOST,
            "tally_port": config.TALLY_PORT,
        }, headers=headers_conn)
    log.info("Heartbeat sent.")

    # Step 5: now trigger the sync job
    log.info("Triggering full sync ...")
    with httpx.Client(timeout=30) as c:
        r = c.post(f"{api_url}/api/tally/sync", headers=headers_user)
        if r.status_code == 200:
            log.info(f"Sync job queued — job_id={r.json().get('job_id', '?')}")
        else:
            log.warning(f"Sync trigger returned {r.status_code}: {r.text[:300]}")

    # Step 6: poll and execute the job
    run_sync(api_url, connector_token, tally, max_wait=120)


if __name__ == "__main__":
    main()
