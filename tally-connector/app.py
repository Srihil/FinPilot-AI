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
    from PIL import Image, ImageDraw, ImageFont
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

# ── Colors ────────────────────────────────────────────────────────────────────
C = {
    "indigo":    "#4f46e5",
    "indigo_lt": "#6366f1",
    "indigo_bg": "#eef2ff",
    "white":     "#ffffff",
    "bg":        "#f8fafc",
    "border":    "#e2e8f0",
    "text":      "#1e293b",
    "muted":     "#64748b",
    "green":     "#16a34a",
    "green_bg":  "#f0fdf4",
    "red":       "#dc2626",
    "red_bg":    "#fef2f2",
    "amber":     "#92400e",
    "amber_bg":  "#fffbeb",
}


# ── Icon helpers (Pillow) ─────────────────────────────────────────────────────

def _circle_img(size: int, color: str, inner: str = None) -> tk.PhotoImage:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([2, 2, size - 2, size - 2], fill=color)
    if inner:
        m = size // 4
        d.ellipse([m, m, size - m, size - m], fill=inner)
    return _to_photo(img)


def _check_img(size: int) -> tk.PhotoImage:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill="#16a34a")
    # checkmark
    pts = [(size*0.25, size*0.52), (size*0.44, size*0.70), (size*0.76, size*0.32)]
    d.line(pts, fill="white", width=max(2, size//10), joint="curve")
    return _to_photo(img)


def _to_photo(img: Image.Image) -> tk.PhotoImage:
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return tk.PhotoImage(data=buf.read())


def _make_tray_icon(connected: bool, tally_online: bool) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bg = (34, 197, 94) if (connected and tally_online) else \
         (251, 191, 36) if connected else (100, 116, 139)
    d.ellipse([4, 4, size - 4, size - 4], fill=bg)
    dot = (34, 197, 94) if tally_online else (239, 68, 68)
    d.ellipse([42, 42, 60, 60], fill=dot, outline=(255, 255, 255), width=2)
    return img


def _update_tray() -> None:
    if not _tray_icon:
        return
    c, t = _state["connected"], _state["tally_online"]
    co = _state["company"]
    title = (f"FinPilot — {co}" if co else "FinPilot — Connected") if (c and t) else \
            "FinPilot — TallyPrime offline" if c else "FinPilot — Not connected"
    _tray_icon.icon = _make_tray_icon(c, t)
    _tray_icon.title = title


# ── Env ───────────────────────────────────────────────────────────────────────

def _save_env(key: str, value: str) -> None:
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = [l for l in content.splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Cloud API ─────────────────────────────────────────────────────────────────

def _h() -> dict:
    return {"Authorization": f"Bearer {config.CONNECTOR_TOKEN}",
            "Content-Type": "application/json"}


def _url(path: str) -> str:
    return config.FINPILOT_API_URL.rstrip("/") + path


def _pair(code: str) -> str:
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
            d = tally.get_vouchers(pl.get("from_date", ""), pl.get("to_date", ""))
            return {"vouchers": d, "count": len(d)}, None
        if op == "READ_SALES":
            d = tally.get_sales(pl.get("from_date", ""), pl.get("to_date", ""))
            return {"sales": d, "count": len(d)}, None
        if op == "READ_PURCHASES":
            d = tally.get_purchases(pl.get("from_date", ""), pl.get("to_date", ""))
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


# ── Worker ────────────────────────────────────────────────────────────────────

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
                _state["error"] = "Token revoked"
                _update_tray()
        except Exception:
            pass
        _stop_event.wait(config.POLL_INTERVAL_SECONDS)


# ── UI helpers ────────────────────────────────────────────────────────────────

def _separator(parent):
    tk.Frame(parent, bg=C["border"], height=1).pack(fill="x", pady=10)


def _label(parent, text, font_size=9, bold=False, color=None, **kwargs):
    f = ("Segoe UI", font_size, "bold") if bold else ("Segoe UI", font_size)
    return tk.Label(parent, text=text, font=f,
                    bg=C["bg"], fg=color or C["text"], **kwargs)


# ── Pairing window ────────────────────────────────────────────────────────────

def _show_pairing_window(on_success=None) -> None:
    win = tk.Tk()
    win.title("FinPilot Connector")
    win.resizable(False, False)
    win.configure(bg=C["bg"])

    W, H = 420, 480
    win.geometry(f"{W}x{H}+{(win.winfo_screenwidth()-W)//2}+{(win.winfo_screenheight()-H)//2}")
    win.lift()
    win.focus_force()

    # ── Header bar ──
    hdr = tk.Frame(win, bg=C["indigo"], height=72)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)

    # Draw a small logo icon
    logo_img = Image.new("RGBA", (36, 36), (0, 0, 0, 0))
    ld = ImageDraw.Draw(logo_img)
    ld.ellipse([0, 0, 35, 35], fill="#ffffff33")
    ld.ellipse([6, 6, 29, 29], fill="white")
    ld.polygon([(18, 9), (26, 24), (10, 24)], fill=C["indigo"])  # lightning bolt shape
    from io import BytesIO
    _buf = BytesIO(); logo_img.save(_buf, "PNG"); _buf.seek(0)
    logo_photo = tk.PhotoImage(data=_buf.read())

    hdr_inner = tk.Frame(hdr, bg=C["indigo"])
    hdr_inner.pack(expand=True)
    tk.Label(hdr_inner, image=logo_photo, bg=C["indigo"]).pack(side="left", padx=(0, 8))
    hdr_inner._logo = logo_photo  # keep reference
    tk.Label(hdr_inner, text="FinPilot Tally Connector",
             font=("Segoe UI", 14, "bold"), fg="white", bg=C["indigo"]).pack(side="left")

    # ── Body ──
    body = tk.Frame(win, bg=C["bg"], padx=28, pady=20)
    body.pack(fill="both", expand=True)

    _label(body, "Connect your TallyPrime to FinPilot AI",
           font_size=11, bold=True).pack(anchor="w")
    _label(body, "Runs silently in your system tray once connected.",
           color=C["muted"]).pack(anchor="w", pady=(2, 12))

    # Steps with numbered badges
    steps = [
        ("1", "Open FinPilot in your browser"),
        ("2", "Go to the TallyPrime page"),
        ("3", "Click  'Connect TallyPrime'"),
        ("4", "Paste the code below and click Connect"),
    ]
    for num, text in steps:
        row = tk.Frame(body, bg=C["bg"])
        row.pack(fill="x", pady=1)
        badge = tk.Label(row, text=num, font=("Segoe UI", 8, "bold"),
                         bg=C["indigo"], fg="white", width=2, relief="flat")
        badge.pack(side="left", padx=(0, 8))
        tk.Label(row, text=text, font=("Segoe UI", 9),
                 bg=C["bg"], fg=C["muted"]).pack(side="left", anchor="w")

    # Open browser button
    browser_btn = tk.Button(body, text="  Open FinPilot in Browser",
                            font=("Segoe UI", 9, "bold"),
                            bg=C["indigo_bg"], fg=C["indigo"],
                            relief="flat", cursor="hand2",
                            padx=12, pady=6, bd=0,
                            activebackground="#dde4ff", activeforeground=C["indigo"],
                            command=lambda: webbrowser.open(FINPILOT_URL))
    browser_btn.pack(anchor="w", pady=(10, 0))

    _separator(body)

    _label(body, "Pairing Code", bold=True, color=C["muted"]).pack(anchor="w")

    code_var = tk.StringVar()
    entry = tk.Entry(body, textvariable=code_var,
                     font=("Courier New", 17, "bold"),
                     width=13, relief="solid", bd=1,
                     highlightthickness=2,
                     highlightcolor=C["indigo"],
                     highlightbackground=C["border"],
                     fg=C["text"], justify="center",
                     insertbackground=C["indigo"])
    entry.pack(anchor="w", ipady=8, pady=(4, 0))
    entry.focus_set()

    # Message label (errors / wakeup hint)
    msg_var = tk.StringVar(value="")
    msg_lbl = tk.Label(body, textvariable=msg_var, font=("Segoe UI", 9),
                       bg=C["bg"], fg=C["red"],
                       wraplength=360, justify="left", anchor="nw")

    _ref = {}   # mutable ref so _do_pair can access btn after creation

    def _do_pair(*_):
        if _ref.get("busy"):
            return
        code = code_var.get().strip()
        if not code:
            msg_lbl.config(fg=C["red"], bg=C["red_bg"])
            msg_var.set("Please enter the pairing code.")
            msg_lbl.pack(fill="x", pady=(8, 0))
            return

        _ref["busy"] = True
        _ref["btn"].config(state="disabled", text="Connecting…",
                           bg=C["indigo_lt"], cursor="watch")
        entry.config(state="disabled")
        msg_var.set("")
        msg_lbl.pack_forget()

        def _wakeup():
            if _ref.get("busy"):
                msg_lbl.config(fg=C["amber"], bg=C["amber_bg"])
                msg_var.set("Waking up server — Render sleeps after inactivity.\nPlease wait up to 60 seconds…")
                msg_lbl.pack(fill="x", pady=(8, 0))
        win.after(6000, _wakeup)

        def _try():
            err = None
            try:
                _pair(code)
                _state["connected"] = True
                win.after(0, _show_success)
                return
            except ValueError as ve:
                err = str(ve)
            except Exception as ex:
                err = f"Network error: {ex}"
            captured = err
            win.after(0, lambda: _show_err(captured))

        threading.Thread(target=_try, daemon=True).start()

    def _show_err(msg: str):
        _ref["busy"] = False
        _ref["btn"].config(state="normal", text="Connect",
                           bg=C["indigo"], cursor="hand2")
        entry.config(state="normal")
        msg_lbl.config(fg=C["red"], bg=C["red_bg"])
        msg_var.set(msg)
        msg_lbl.pack(fill="x", pady=(8, 0))
        entry.focus_set()

    def _show_success():
        for w in body.winfo_children():
            w.destroy()

        # Success icon
        check = _check_img(52)
        icon_lbl = tk.Label(body, image=check, bg=C["bg"])
        icon_lbl.image = check
        icon_lbl.pack(pady=(24, 8))

        _label(body, "Connected!", font_size=18, bold=True,
               color=C["green"]).pack()

        co = _state.get("company", "")
        if co:
            _label(body, f"Company:  {co}", color=C["muted"]).pack(pady=(4, 0))

        # Green info box
        info = tk.Frame(body, bg=C["green_bg"], padx=14, pady=10)
        info.pack(fill="x", pady=14)

        # Draw small info dot
        dot_img = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
        ImageDraw.Draw(dot_img).ellipse([0, 0, 9, 9], fill="#16a34a")
        _dbuf = BytesIO(); dot_img.save(_dbuf, "PNG"); _dbuf.seek(0)
        dot_ph = tk.PhotoImage(data=_dbuf.read())

        dot_row = tk.Frame(info, bg=C["green_bg"])
        dot_row.pack(fill="x")
        dot_lbl = tk.Label(dot_row, image=dot_ph, bg=C["green_bg"])
        dot_lbl.image = dot_ph
        dot_lbl.pack(side="left", padx=(0, 6))
        tk.Label(dot_row, text="Connector is running in your system tray",
                 font=("Segoe UI", 9, "bold"), bg=C["green_bg"],
                 fg=C["green"]).pack(side="left")

        tk.Label(info, text="Look for the FinPilot icon near your clock\n(bottom-right corner of taskbar).",
                 font=("Segoe UI", 9), bg=C["green_bg"],
                 fg="#166534").pack(anchor="w")

        close_btn = tk.Button(body, text="Close Window",
                              font=("Segoe UI", 10, "bold"),
                              bg=C["indigo"], fg="white",
                              relief="flat", cursor="hand2",
                              padx=20, pady=9, bd=0,
                              activebackground=C["indigo_lt"],
                              activeforeground="white",
                              command=win.destroy)
        close_btn.pack(pady=(4, 0))

        _update_tray()
        if on_success:
            threading.Thread(target=on_success, daemon=True).start()

    # Connect button
    btn = tk.Button(body, text="Connect",
                    font=("Segoe UI", 11, "bold"),
                    bg=C["indigo"], fg="white",
                    relief="flat", cursor="hand2",
                    padx=22, pady=10, bd=0,
                    activebackground=C["indigo_lt"],
                    activeforeground="white",
                    command=_do_pair)
    btn.pack(anchor="w", pady=(12, 0))
    _ref["btn"] = btn

    entry.bind("<Return>", _do_pair)
    win.bind("<Return>", _do_pair)
    win.mainloop()


# ── Status window ─────────────────────────────────────────────────────────────

def _show_status_window() -> None:
    win = tk.Tk()
    win.title("FinPilot Connector")
    win.resizable(False, False)
    win.configure(bg=C["bg"])
    W, H = 360, 290
    win.geometry(f"{W}x{H}+{(win.winfo_screenwidth()-W)//2}+{(win.winfo_screenheight()-H)//2}")
    win.lift(); win.focus_force()

    hdr = tk.Frame(win, bg=C["indigo"], height=60)
    hdr.pack(fill="x"); hdr.pack_propagate(False)
    tk.Label(hdr, text="FinPilot Tally Connector",
             font=("Segoe UI", 12, "bold"), fg="white", bg=C["indigo"]).pack(expand=True)

    body = tk.Frame(win, bg=C["bg"], padx=28, pady=20)
    body.pack(fill="both", expand=True)

    connected = _state["connected"]
    tally_on = _state["tally_online"]

    # Status indicator row
    status_row = tk.Frame(body, bg=C["bg"])
    status_row.pack(anchor="w", pady=(0, 8))

    dot_color = C["green"] if (connected and tally_on) else "#f59e0b" if connected else C["red"]
    dot = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
    ImageDraw.Draw(dot).ellipse([0, 0, 11, 11], fill=dot_color)
    from io import BytesIO as _B
    _db = _B(); dot.save(_db, "PNG"); _db.seek(0)
    dot_ph = tk.PhotoImage(data=_db.read())
    dot_lbl = tk.Label(status_row, image=dot_ph, bg=C["bg"])
    dot_lbl.image = dot_ph
    dot_lbl.pack(side="left", padx=(0, 6))

    status_text = "Connected" if (connected and tally_on) else \
                  "Connector active — TallyPrime offline" if connected else "Not connected"
    tk.Label(status_row, text=status_text,
             font=("Segoe UI", 12, "bold"), bg=C["bg"],
             fg=C["green"] if (connected and tally_on) else C["text"]).pack(side="left")

    co = _state["company"] or "detecting…"
    for label, val in [("Company", co),
                       ("Tally", f"{config.TALLY_HOST}:{config.TALLY_PORT}"),
                       ("Backend", config.FINPILOT_API_URL)]:
        row = tk.Frame(body, bg=C["bg"])
        row.pack(fill="x", pady=1)
        tk.Label(row, text=f"{label}:", font=("Segoe UI", 9, "bold"),
                 width=8, anchor="w", bg=C["bg"], fg=C["muted"]).pack(side="left")
        tk.Label(row, text=val, font=("Segoe UI", 9),
                 bg=C["bg"], fg=C["text"]).pack(side="left")

    tk.Label(body, text="Running in system tray. Safe to close this window.",
             font=("Segoe UI", 8), bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(10, 0))

    tk.Button(body, text="Close",
              font=("Segoe UI", 10, "bold"),
              bg=C["indigo"], fg="white",
              relief="flat", cursor="hand2",
              padx=18, pady=7, bd=0,
              activebackground=C["indigo_lt"],
              command=win.destroy).pack(pady=(12, 0))

    win.mainloop()


# ── Tray ──────────────────────────────────────────────────────────────────────

def _tray_status(icon, item):
    threading.Thread(target=_show_status_window, daemon=True).start()


def _tray_open(icon, item):
    webbrowser.open(FINPILOT_URL)


def _tray_repair(icon, item):
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
        _make_tray_icon(False, False),
        "FinPilot Connector",
        pystray.Menu(
            pystray.MenuItem("Status", _tray_status, default=True),
            pystray.MenuItem("Open FinPilot", _tray_open),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Disconnect & Re-pair", _tray_repait := _tray_repair),
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
