"""
FinPilot Tally Connector — System Tray App
"""
import socket
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from typing import Optional

try:
    import httpx
    import pystray
    from PIL import Image, ImageDraw
    from config import config, BASE_DIR
    from tally_client import TallyClient, TallyError
except Exception as _e:
    import tkinter.messagebox as _mb
    _r = tk.Tk(); _r.withdraw()
    _mb.showerror("FinPilot Connector", f"Startup failed:\n\n{type(_e).__name__}: {_e}")
    sys.exit(1)

FINPILOT_URL = "https://finpilot-frontend-vbdf.onrender.com/tally"
ENV_FILE = BASE_DIR / ".env"

_state = {"connected": False, "tally_online": False, "company": "", "error": ""}
_tray_icon: Optional[pystray.Icon] = None
_stop_event = threading.Event()

ALLOWED_OPS = {
    "READ_COMPANIES", "READ_LEDGERS", "READ_VOUCHERS", "READ_SALES",
    "READ_PURCHASES", "READ_RECEIVABLES", "READ_PAYABLES", "READ_STOCK_ITEMS",
    "CREATE_SALES_VOUCHER", "CREATE_PURCHASE_VOUCHER", "CREATE_RECEIPT_VOUCHER",
    "CREATE_PAYMENT_VOUCHER", "CREATE_LEDGER", "CREATE_STOCK_ITEM",
    "SYNC_FULL", "SYNC_PARTIAL",
}


# ── Env ───────────────────────────────────────────────────────────────────────

def _save_env(key: str, value: str) -> None:
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = [l for l in content.splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Tray icon ─────────────────────────────────────────────────────────────────

def _make_icon(connected: bool, tally_online: bool) -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (34, 197, 94) if (connected and tally_online) else \
         (251, 191, 36) if connected else (100, 116, 139)
    d.ellipse([4, 4, 60, 60], fill=bg)
    dot = (34, 197, 94) if tally_online else (239, 68, 68)
    d.ellipse([42, 42, 60, 60], fill=dot, outline=(255, 255, 255), width=2)
    return img


def _update_tray() -> None:
    if not _tray_icon:
        return
    c, t = _state["connected"], _state["tally_online"]
    co = _state["company"]
    if c and t:
        title = f"FinPilot ● {co}" if co else "FinPilot ● Connected"
    elif c:
        title = "FinPilot ◌ TallyPrime offline"
    else:
        title = "FinPilot ○ Not connected"
    _tray_icon.icon = _make_icon(c, t)
    _tray_icon.title = title


# ── Cloud API ─────────────────────────────────────────────────────────────────

def _h() -> dict:
    return {"Authorization": f"Bearer {config.CONNECTOR_TOKEN}",
            "Content-Type": "application/json"}


def _url(path: str) -> str:
    return config.FINPILOT_API_URL.rstrip("/") + path


def _pair(code: str) -> str:
    # 70s timeout — Render free tier can take up to 60s to wake from sleep
    with httpx.Client(timeout=70) as c:
        r = c.post(_url("/api/tally/connector/register"),
                   json={"pairing_code": code.strip().upper(),
                         "connector_name": "FinPilot Connector",
                         "device_name": socket.gethostname()},
                   headers={"Content-Type": "application/json"})
        if r.status_code == 400:
            raise ValueError(r.json().get("detail", "Invalid pairing code"))
        r.raise_for_status()
        token = r.json()["token"]
    _save_env("CONNECTOR_TOKEN", token)
    config.CONNECTOR_TOKEN = token
    return token


def _heartbeat(tally: TallyClient) -> None:
    reachable = tally.is_reachable()
    company = None
    if reachable:
        info = tally.get_active_company()
        if info:
            company = info.get("name", "")
    _state["tally_online"] = reachable
    _state["company"] = company or ""
    with httpx.Client(timeout=10) as c:
        c.post(_url("/api/tally/connector/heartbeat"),
               json={"tally_reachable": reachable, "tally_company_name": company,
                     "tally_host": config.TALLY_HOST, "tally_port": config.TALLY_PORT},
               headers=_h())
    _update_tray()


def _execute_job(tally: TallyClient, job: dict):
    op = job.get("operation", "")
    pl = job.get("payload") or {}
    if op not in ALLOWED_OPS:
        return None, f"Operation not allowed: {op}"
    try:
        if op == "READ_COMPANIES":
            return {"company": tally.get_active_company()}, None
        if op == "READ_LEDGERS":
            d = tally.get_ledgers(); return {"ledgers": d, "count": len(d)}, None
        if op == "READ_VOUCHERS":
            d = tally.get_vouchers(pl.get("from_date",""), pl.get("to_date",""))
            return {"vouchers": d, "count": len(d)}, None
        if op == "READ_SALES":
            d = tally.get_sales(pl.get("from_date",""), pl.get("to_date",""))
            return {"sales": d, "count": len(d)}, None
        if op == "READ_PURCHASES":
            d = tally.get_purchases(pl.get("from_date",""), pl.get("to_date",""))
            return {"purchases": d, "count": len(d)}, None
        if op == "READ_RECEIVABLES":
            d = tally.get_receivables(); return {"receivables": d, "count": len(d)}, None
        if op == "READ_PAYABLES":
            d = tally.get_payables(); return {"payables": d, "count": len(d)}, None
        if op == "READ_STOCK_ITEMS":
            d = tally.get_stock_items(); return {"stock_items": d, "count": len(d)}, None
        if op == "CREATE_SALES_VOUCHER":
            return tally.create_sales_voucher(pl), None
        if op == "CREATE_PURCHASE_VOUCHER":
            return tally.create_purchase_voucher(pl), None
        if op == "CREATE_LEDGER":
            return tally.create_ledger(pl), None
        if op in ("SYNC_FULL", "SYNC_PARTIAL"):
            led = tally.get_ledgers(); stk = tally.get_stock_items()
            return {"synced": True, "ledger_count": len(led), "stock_item_count": len(stk)}, None
        return None, f"Not implemented: {op}"
    except TallyError as e:
        return None, str(e)
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _poll(tally: TallyClient) -> None:
    with httpx.Client(timeout=15) as c:
        r = c.get(_url("/api/tally/connector/jobs"), headers=_h())
        r.raise_for_status()
        jobs = r.json().get("jobs", [])
    for job in jobs:
        result, error = _execute_job(tally, job)
        payload = {"status": "SUCCESS" if error is None else "FAILED"}
        if result:
            payload["result"] = result
        if error:
            payload["error_message"] = error
        with httpx.Client(timeout=15) as c:
            c.post(_url(f"/api/tally/connector/jobs/{job['id']}/result"),
                   json=payload, headers=_h())


# ── Worker thread ─────────────────────────────────────────────────────────────

def _worker() -> None:
    tally = TallyClient(host=config.TALLY_HOST, port=config.TALLY_PORT)
    last_hb = 0.0
    while not _stop_event.is_set():
        try:
            now = time.time()
            if now - last_hb >= config.HEARTBEAT_INTERVAL_SECONDS:
                _heartbeat(tally)
                last_hb = now
            _poll(tally)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                _state["connected"] = False
                _state["error"] = "Token revoked — re-pair needed"
                _update_tray()
        except Exception:
            pass
        _stop_event.wait(config.POLL_INTERVAL_SECONDS)


# ── Pairing window ────────────────────────────────────────────────────────────

def _show_pairing_window(on_success=None) -> None:
    win = tk.Tk()
    win.title("FinPilot — Connect TallyPrime")
    win.resizable(False, False)
    win.configure(bg="#f8fafc")

    W, H = 440, 390
    win.geometry(f"{W}x{H}+{(win.winfo_screenwidth()-W)//2}+{(win.winfo_screenheight()-H)//2}")
    win.lift()
    win.focus_force()

    # Header
    hdr = tk.Frame(win, bg="#4f46e5", height=64)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)
    tk.Label(hdr, text="⚡  FinPilot Tally Connector",
             font=("Segoe UI", 13, "bold"), fg="white", bg="#4f46e5").pack(expand=True)

    # Body — fixed inner frame so button never gets hidden
    body = tk.Frame(win, bg="#f8fafc", padx=28, pady=18)
    body.pack(fill="both", expand=True)

    tk.Label(body, text="Connect your TallyPrime to FinPilot AI",
             font=("Segoe UI", 11, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")
    tk.Label(body, text="Runs silently in your system tray once connected.",
             font=("Segoe UI", 9), bg="#f8fafc", fg="#64748b").pack(anchor="w", pady=(2, 10))

    # Steps
    for s in ["1.  Open FinPilot in your browser (button below)",
              "2.  Go to the TallyPrime page",
              "3.  Click  'Connect TallyPrime'",
              "4.  Paste the pairing code below and press Enter"]:
        tk.Label(body, text=s, font=("Segoe UI", 9), bg="#f8fafc",
                 fg="#475569", anchor="w").pack(fill="x")

    # Open browser
    tk.Button(body, text="🌐  Open FinPilot →",
              font=("Segoe UI", 9, "bold"), bg="#e0e7ff", fg="#4338ca",
              relief="flat", cursor="hand2", padx=10, pady=5,
              command=lambda: webbrowser.open(FINPILOT_URL)
              ).pack(anchor="w", pady=(10, 0))

    tk.Frame(body, bg="#e2e8f0", height=1).pack(fill="x", pady=12)

    tk.Label(body, text="Pairing Code", font=("Segoe UI", 9, "bold"),
             bg="#f8fafc", fg="#374151").pack(anchor="w")

    code_var = tk.StringVar()
    entry = tk.Entry(body, textvariable=code_var,
                     font=("Courier New", 16, "bold"),
                     width=14, relief="solid", bd=1,
                     fg="#1e293b", justify="center", insertbackground="#4f46e5")
    entry.pack(anchor="w", ipady=7, pady=(4, 2))
    entry.focus_set()

    hint_var = tk.StringVar(value="Press Enter to connect")
    hint_lbl = tk.Label(body, textvariable=hint_var,
                        font=("Segoe UI", 9), bg="#f8fafc", fg="#94a3b8")
    hint_lbl.pack(anchor="w")

    msg_var = tk.StringVar(value="")
    msg_lbl = tk.Label(body, textvariable=msg_var, font=("Segoe UI", 9),
                       bg="#f8fafc", fg="#dc2626",
                       wraplength=380, justify="left", anchor="nw")

    _busy = {"v": False}

    def _do_pair(*args):
        print(f"[DEBUG] _do_pair called, args={args}, busy={_busy['v']}", flush=True)
        if _busy["v"]:
            print("[DEBUG] Already busy, returning", flush=True)
            return
        code = code_var.get().strip()
        print(f"[DEBUG] Code entered: '{code}'", flush=True)
        if not code:
            msg_lbl.config(fg="#dc2626", bg="#fef2f2")
            msg_var.set("⚠  Please enter the pairing code.")
            msg_lbl.pack(fill="x", pady=(6, 0))
            return

        _busy["v"] = True
        entry.config(state="disabled")
        hint_var.set("Connecting…")
        hint_lbl.config(fg="#4f46e5")
        msg_var.set("")
        msg_lbl.pack_forget()

        def _wakeup_hint():
            if _busy["v"]:
                msg_lbl.config(fg="#92400e", bg="#fffbeb")
                msg_var.set("⏳  Waking up server — Render free tier sleeps after inactivity.\n    Please wait up to 60 seconds…")
                msg_lbl.pack(fill="x", pady=(6, 0))
        win.after(6000, _wakeup_hint)

        def _try():
            print(f"[DEBUG] _try thread started, calling _pair with code={code}", flush=True)
            err = None
            try:
                _pair(code)
                print("[DEBUG] _pair succeeded", flush=True)
                _state["connected"] = True
                win.after(0, _show_success)
                return
            except ValueError as ve:
                print(f"[DEBUG] ValueError: {ve}", flush=True)
                err = f"❌  {ve}"
            except Exception as ex:
                print(f"[DEBUG] Exception: {type(ex).__name__}: {ex}", flush=True)
                err = f"❌  Network error: {ex}"
            captured = err
            win.after(0, lambda: _show_err(captured))

        print("[DEBUG] Starting _try thread", flush=True)
        threading.Thread(target=_try, daemon=True).start()
        print("[DEBUG] _try thread started", flush=True)

    def _show_err(msg: str):
        _busy["v"] = False
        entry.config(state="normal")
        hint_var.set("Press Enter to connect")
        hint_lbl.config(fg="#94a3b8")
        msg_lbl.config(fg="#dc2626", bg="#fef2f2")
        msg_var.set(msg)
        msg_lbl.pack(fill="x", pady=(6, 0))
        entry.focus_set()

    def _show_success():
        for w in body.winfo_children():
            w.destroy()
        tk.Label(body, text="✅  Connected!",
                 font=("Segoe UI", 20, "bold"), bg="#f8fafc", fg="#16a34a").pack(pady=(30, 6))
        co = _state.get("company", "")
        tk.Label(body,
                 text="TallyPrime is now linked to FinPilot AI." + (f"\nCompany: {co}" if co else ""),
                 font=("Segoe UI", 10), bg="#f8fafc", fg="#475569").pack()
        tk.Label(body, text="\nConnector is running in your system tray\n(bottom-right corner).",
                 font=("Segoe UI", 9), bg="#f8fafc", fg="#64748b").pack()
        tk.Button(body, text="Close this window",
                  font=("Segoe UI", 10, "bold"), bg="#4f46e5", fg="white",
                  relief="flat", cursor="hand2", padx=14, pady=8,
                  command=win.destroy).pack(pady=20)
        _update_tray()
        if on_success:
            threading.Thread(target=on_success, daemon=True).start()

    # Bind on the Entry (not the window) so it fires when Entry has focus
    print("[DEBUG] Binding <Return> to entry and window", flush=True)
    entry.bind("<Return>", _do_pair)
    win.bind("<Return>", _do_pair)
    print("[DEBUG] Bindings done, starting mainloop", flush=True)
    win.mainloop()


# ── Status window ─────────────────────────────────────────────────────────────

def _show_status_window() -> None:
    win = tk.Tk()
    win.title("FinPilot Connector — Status")
    win.resizable(False, False)
    win.configure(bg="#f8fafc")
    W, H = 360, 280
    win.geometry(f"{W}x{H}+{(win.winfo_screenwidth()-W)//2}+{(win.winfo_screenheight()-H)//2}")
    win.lift(); win.focus_force()

    hdr = tk.Frame(win, bg="#4f46e5", height=60)
    hdr.pack(fill="x"); hdr.pack_propagate(False)
    tk.Label(hdr, text="⚡  FinPilot Tally Connector",
             font=("Segoe UI", 12, "bold"), fg="white", bg="#4f46e5").pack(expand=True)

    body = tk.Frame(win, bg="#f8fafc", padx=28, pady=20)
    body.pack(fill="both", expand=True)

    dot = "🟢" if (_state["connected"] and _state["tally_online"]) else \
          "🟡" if _state["connected"] else "🔴"
    tk.Label(body, text=f"{dot}  Connected",
             font=("Segoe UI", 14, "bold"), bg="#f8fafc", fg="#1e293b").pack(anchor="w")

    co = _state["company"] or "detecting…"
    for label, val in [("Company", co),
                       ("Tally", f"{config.TALLY_HOST}:{config.TALLY_PORT}"),
                       ("Backend", config.FINPILOT_API_URL)]:
        tk.Label(body, text=f"{label}:  {val}",
                 font=("Segoe UI", 9), bg="#f8fafc", fg="#475569").pack(anchor="w", pady=1)

    tk.Label(body, text="\nRunning in system tray. Safe to close this window.",
             font=("Segoe UI", 9), bg="#f8fafc", fg="#94a3b8").pack(anchor="w")

    tk.Button(body, text="Close", font=("Segoe UI", 10, "bold"),
              bg="#4f46e5", fg="white", relief="flat", cursor="hand2",
              padx=16, pady=7, command=win.destroy).pack(pady=(14, 0))

    win.mainloop()


# ── Tray actions ──────────────────────────────────────────────────────────────

def _tray_status(icon, item):
    threading.Thread(target=_show_status_window, daemon=True).start()


def _tray_open(icon, item):
    webbrowser.open(FINPILOT_URL)


def _tray_repear(icon, item):
    _save_env("CONNECTOR_TOKEN", "")
    config.CONNECTOR_TOKEN = ""
    _state.update({"connected": False, "tally_online": False, "company": ""})
    _update_tray()
    threading.Thread(
        target=lambda: _show_pairing_window(
            on_success=lambda: _state.update({"connected": True})
        ), daemon=True
    ).start()


def _tray_exit(icon, item):
    _stop_event.set()
    icon.stop()
    sys.exit(0)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    global _tray_icon

    if not config.CONNECTOR_TOKEN:
        paired = threading.Event()

        def _after():
            _state["connected"] = True
            paired.set()
            threading.Thread(target=_worker, daemon=True).start()

        _show_pairing_window(on_success=_after)
        if not config.CONNECTOR_TOKEN:
            sys.exit(0)
        paired.wait(timeout=5)
    else:
        _state["connected"] = True
        threading.Thread(target=_worker, daemon=True).start()
        threading.Thread(target=_show_status_window, daemon=True).start()

    _tray_icon = pystray.Icon(
        "finpilot",
        _make_icon(False, False),
        "FinPilot Connector",
        pystray.Menu(
            pystray.MenuItem("Status", _tray_status, default=True),
            pystray.MenuItem("Open FinPilot", _tray_open),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Disconnect & Re-pair", _tray_repear),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", _tray_exit),
        ),
    )
    _update_tray()
    _tray_icon.run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import tkinter.messagebox as mb
        r = tk.Tk(); r.withdraw()
        mb.showerror("FinPilot Connector", traceback.format_exc())
        sys.exit(1)
