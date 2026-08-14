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
from io import BytesIO
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

C = {
    "indigo":     "#4f46e5",
    "indigo_lt":  "#6366f1",
    "indigo_bg":  "#eef2ff",
    "white":      "#ffffff",
    "bg":         "#f8fafc",
    "border":     "#e2e8f0",
    "text":       "#1e293b",
    "muted":      "#64748b",
    "green":      "#16a34a",
    "green_bg":   "#f0fdf4",
    "green_text": "#166534",
    "red":        "#dc2626",
    "red_bg":     "#fef2f2",
    "red_text":   "#991b1b",
    "amber":      "#b45309",
    "amber_bg":   "#fffbeb",
}


# ── PIL helpers ───────────────────────────────────────────────────────────────

def _to_photo(img: Image.Image) -> tk.PhotoImage:
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return tk.PhotoImage(data=buf.read())


def _make_logo(size=36) -> tk.PhotoImage:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill="white")
    # Simple "F" letterform in indigo
    m = size // 6
    d.rectangle([m * 2, m, m * 2 + 3, size - m], fill="#4f46e5")
    d.rectangle([m * 2, m, m * 4, m + 3], fill="#4f46e5")
    d.rectangle([m * 2, size // 2 - 1, m * 3 + 4, size // 2 + 2], fill="#4f46e5")
    return _to_photo(img)


def _make_check(size=48) -> tk.PhotoImage:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, size - 1, size - 1], fill="#16a34a")
    s = size
    pts = [(s * .22, s * .52), (s * .42, s * .70), (s * .75, s * .30)]
    d.line(pts, fill="white", width=max(3, size // 12), joint="curve")
    return _to_photo(img)


def _make_dot(size=10, color="#16a34a") -> tk.PhotoImage:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse([0, 0, size - 1, size - 1], fill=color)
    return _to_photo(img)


def _make_tray_icon(connected: bool, tally_online: bool) -> Image.Image:
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
            detail = r.json().get("detail", "Invalid pairing code")
            raise ValueError(detail)
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
            return {"synced": True, "ledger_count": len(led),
                    "stock_item_count": len(stk)}, None
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


# ── Pairing window ────────────────────────────────────────────────────────────

def _user_friendly_error(exc: Exception) -> tuple[str, str]:
    """Return (title, detail) for an exception."""
    msg = str(exc)
    if isinstance(exc, ValueError):
        if "expired" in msg.lower() or "invalid" in msg.lower():
            return (
                "Invalid or expired pairing code",
                "Codes expire after 10 minutes. Go to FinPilot → TallyPrime and click 'Connect TallyPrime' to get a fresh code."
            )
        return ("Pairing failed", msg)

    if isinstance(exc, httpx.ConnectError):
        return (
            "Cannot reach FinPilot server",
            "Check your internet connection. If the problem persists, the server may be down."
        )
    if isinstance(exc, httpx.TimeoutException):
        return (
            "Connection timed out",
            "The server took too long to respond. Render free tier can take up to 60 seconds to wake up. Please try again."
        )
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return ("Unauthorized", "Your token was rejected. Please re-pair.")
        if code == 500:
            return ("Server error", "FinPilot server returned an error. Please try again in a moment.")
        return ("Server error", f"HTTP {code} — {msg}")

    return ("Connection error", f"Unexpected error: {type(exc).__name__}: {msg}")


def _show_pairing_window(on_success=None) -> None:
    win = tk.Tk()
    win.title("FinPilot Connector")
    win.resizable(False, False)
    win.configure(bg=C["bg"])

    W, H = 420, 500
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
    win.lift()
    win.focus_force()

    # ── Header ──
    hdr = tk.Frame(win, bg=C["indigo"], height=68)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)

    logo_ph = _make_logo(32)
    hdr_row = tk.Frame(hdr, bg=C["indigo"])
    hdr_row.pack(expand=True)
    logo_lbl = tk.Label(hdr_row, image=logo_ph, bg=C["indigo"])
    logo_lbl.image = logo_ph
    logo_lbl.pack(side="left", padx=(0, 10))
    tk.Label(hdr_row, text="FinPilot Tally Connector",
             font=("Segoe UI", 13, "bold"), fg="white", bg=C["indigo"]).pack(side="left")

    # ── Body ──
    body = tk.Frame(win, bg=C["bg"], padx=28, pady=16)
    body.pack(fill="both", expand=True)

    tk.Label(body, text="Connect your TallyPrime to FinPilot AI",
             font=("Segoe UI", 11, "bold"), bg=C["bg"], fg=C["text"]).pack(anchor="w")
    tk.Label(body, text="Runs silently in your system tray once connected.",
             font=("Segoe UI", 9), bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(2, 10))

    # Steps
    for num, text in [("1", "Open FinPilot in your browser"),
                      ("2", "Go to the TallyPrime page"),
                      ("3", "Click 'Connect TallyPrime'"),
                      ("4", "Paste the code below and click Connect")]:
        row = tk.Frame(body, bg=C["bg"])
        row.pack(fill="x", pady=1)
        tk.Label(row, text=num, font=("Segoe UI", 8, "bold"),
                 bg=C["indigo"], fg="white", width=2).pack(side="left", padx=(0, 8))
        tk.Label(row, text=text, font=("Segoe UI", 9),
                 bg=C["bg"], fg=C["muted"]).pack(side="left")

    tk.Button(body, text="  Open FinPilot in Browser",
              font=("Segoe UI", 9, "bold"), bg=C["indigo_bg"], fg=C["indigo"],
              relief="flat", cursor="hand2", padx=12, pady=5, bd=0,
              activebackground="#dde4ff",
              command=lambda: webbrowser.open(FINPILOT_URL)).pack(anchor="w", pady=(8, 0))

    tk.Frame(body, bg=C["border"], height=1).pack(fill="x", pady=10)

    tk.Label(body, text="Pairing Code", font=("Segoe UI", 9, "bold"),
             bg=C["bg"], fg=C["muted"]).pack(anchor="w")

    code_var = tk.StringVar()
    entry = tk.Entry(body, textvariable=code_var,
                     font=("Courier New", 17, "bold"), width=13,
                     relief="solid", bd=1,
                     highlightthickness=2,
                     highlightcolor=C["indigo"],
                     highlightbackground=C["border"],
                     fg=C["text"], justify="center",
                     insertbackground=C["indigo"])
    entry.pack(anchor="w", ipady=8, pady=(4, 0))
    entry.focus_set()

    # ── Message box — ALWAYS in layout, between entry and button ──
    # Using a Frame so we can show/hide it cleanly without affecting button position
    msg_frame = tk.Frame(body, bg=C["bg"])
    msg_frame.pack(fill="x", pady=(6, 0))
    msg_frame.pack_propagate(False)
    msg_frame.config(height=1)   # collapsed by default

    msg_title_var = tk.StringVar(value="")
    msg_body_var = tk.StringVar(value="")

    msg_inner = tk.Frame(msg_frame, bg=C["red_bg"],
                         highlightbackground=C["red"], highlightthickness=1)
    msg_title_lbl = tk.Label(msg_inner, textvariable=msg_title_var,
                             font=("Segoe UI", 9, "bold"),
                             bg=C["red_bg"], fg=C["red_text"],
                             anchor="w", justify="left", wraplength=360)
    msg_body_lbl = tk.Label(msg_inner, textvariable=msg_body_var,
                            font=("Segoe UI", 8),
                            bg=C["red_bg"], fg=C["red_text"],
                            anchor="w", justify="left", wraplength=360)

    def _show_msg(title: str, detail: str, style: str = "error") -> None:
        bg = C["red_bg"] if style == "error" else C["amber_bg"]
        fg = C["red_text"] if style == "error" else C["amber"]
        border = C["red"] if style == "error" else "#d97706"
        msg_inner.config(bg=bg, highlightbackground=border)
        msg_title_lbl.config(bg=bg, fg=fg, text=title)
        msg_body_lbl.config(bg=bg, fg=fg, text=detail)
        msg_title_lbl.pack(anchor="w", padx=10, pady=(8, 2))
        msg_body_lbl.pack(anchor="w", padx=10, pady=(0, 8))
        msg_inner.pack(fill="x")
        # Expand the frame to fit content
        msg_frame.config(height=56 if detail else 34)
        win.update_idletasks()

    def _hide_msg() -> None:
        msg_inner.pack_forget()
        msg_title_lbl.pack_forget()
        msg_body_lbl.pack_forget()
        msg_frame.config(height=1)

    # ── Connect button — always below msg_frame ──
    btn_frame = tk.Frame(body, bg=C["bg"])
    btn_frame.pack(anchor="w", pady=(10, 0))

    _ref = {"busy": False}

    def _do_pair(*_):
        if _ref["busy"]:
            return

        # Auto-strip spaces from pasted code
        raw = code_var.get().strip().replace(" ", "").upper()
        code_var.set(raw)

        if not raw:
            _show_msg("No code entered",
                      "Paste the pairing code from the FinPilot TallyPrime page.")
            entry.focus_set()
            return

        if len(raw.replace("-", "")) < 8:
            _show_msg("Code too short",
                      "A valid pairing code looks like  ABCD-EFGHI  (9 characters).")
            entry.focus_set()
            return

        _ref["busy"] = True
        _hide_msg()
        btn.config(state="disabled", text="Connecting…", bg=C["indigo_lt"], cursor="watch")
        entry.config(state="disabled",
                     highlightbackground=C["border"],
                     highlightcolor=C["border"])

        # Wakeup hint after 6 seconds
        def _wakeup():
            if _ref["busy"]:
                _show_msg("Waking up server…",
                          "Render free tier sleeps after inactivity and can take up to 60 seconds to wake. Please wait.",
                          style="warn")
        win.after(6000, _wakeup)

        def _try():
            try:
                _pair(raw)
                _state["connected"] = True
                win.after(0, _show_success)
            except Exception as exc:
                title, detail = _user_friendly_error(exc)
                win.after(0, lambda t=title, d=detail: _show_err(t, d))

        threading.Thread(target=_try, daemon=True).start()

    def _show_err(title: str, detail: str) -> None:
        _ref["busy"] = False
        btn.config(state="normal", text="Connect", bg=C["indigo"], cursor="hand2")
        # Red highlight on entry
        entry.config(state="normal",
                     highlightbackground=C["red"],
                     highlightcolor=C["red"])
        # Clear the code so user can type a fresh one
        code_var.set("")
        _show_msg(title, detail, style="error")
        entry.focus_set()

    def _show_success() -> None:
        for w in body.winfo_children():
            w.destroy()

        check_ph = _make_check(52)
        ck = tk.Label(body, image=check_ph, bg=C["bg"])
        ck.image = check_ph
        ck.pack(pady=(28, 6))

        tk.Label(body, text="Connected!",
                 font=("Segoe UI", 18, "bold"), bg=C["bg"],
                 fg=C["green"]).pack()

        co = _state.get("company", "")
        if co:
            tk.Label(body, text=f"Company:  {co}",
                     font=("Segoe UI", 10), bg=C["bg"],
                     fg=C["muted"]).pack(pady=(4, 0))

        info = tk.Frame(body, bg=C["green_bg"])
        info.pack(fill="x", pady=14, padx=0)

        dot_ph = _make_dot(10, C["green"])
        dot_row = tk.Frame(info, bg=C["green_bg"])
        dot_row.pack(fill="x", padx=14, pady=(10, 2))
        dl = tk.Label(dot_row, image=dot_ph, bg=C["green_bg"])
        dl.image = dot_ph
        dl.pack(side="left", padx=(0, 6))
        tk.Label(dot_row, text="Connector is running in your system tray",
                 font=("Segoe UI", 9, "bold"), bg=C["green_bg"],
                 fg=C["green"]).pack(side="left")
        tk.Label(info,
                 text="Look for the FinPilot icon near your clock (bottom-right corner).",
                 font=("Segoe UI", 9), bg=C["green_bg"],
                 fg=C["green_text"]).pack(anchor="w", padx=14, pady=(0, 10))

        tk.Button(body, text="Close Window",
                  font=("Segoe UI", 10, "bold"),
                  bg=C["indigo"], fg="white",
                  relief="flat", cursor="hand2",
                  padx=20, pady=8, bd=0,
                  activebackground=C["indigo_lt"],
                  command=win.destroy).pack(pady=(4, 0))

        _update_tray()
        if on_success:
            threading.Thread(target=on_success, daemon=True).start()

    btn = tk.Button(btn_frame, text="Connect",
                    font=("Segoe UI", 11, "bold"),
                    bg=C["indigo"], fg="white",
                    relief="flat", cursor="hand2",
                    padx=22, pady=9, bd=0,
                    activebackground=C["indigo_lt"],
                    activeforeground="white",
                    command=_do_pair)
    btn.pack(side="left")
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
    W, H = 360, 280
    sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
    win.geometry(f"{W}x{H}+{(sw - W) // 2}+{(sh - H) // 2}")
    win.lift()
    win.focus_force()

    hdr = tk.Frame(win, bg=C["indigo"], height=58)
    hdr.pack(fill="x")
    hdr.pack_propagate(False)
    logo_ph = _make_logo(28)
    hdr_row = tk.Frame(hdr, bg=C["indigo"])
    hdr_row.pack(expand=True)
    ll = tk.Label(hdr_row, image=logo_ph, bg=C["indigo"])
    ll.image = logo_ph
    ll.pack(side="left", padx=(0, 8))
    tk.Label(hdr_row, text="FinPilot Tally Connector",
             font=("Segoe UI", 11, "bold"), fg="white", bg=C["indigo"]).pack(side="left")

    body = tk.Frame(win, bg=C["bg"], padx=28, pady=18)
    body.pack(fill="both", expand=True)

    connected = _state["connected"]
    tally_on = _state["tally_online"]
    dot_color = C["green"] if (connected and tally_on) else "#f59e0b" if connected else C["red"]
    dot_ph = _make_dot(11, dot_color)

    status_row = tk.Frame(body, bg=C["bg"])
    status_row.pack(anchor="w", pady=(0, 10))
    dl = tk.Label(status_row, image=dot_ph, bg=C["bg"])
    dl.image = dot_ph
    dl.pack(side="left", padx=(0, 7))
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

    tk.Label(body, text="Running in system tray — safe to close this window.",
             font=("Segoe UI", 8), bg=C["bg"], fg=C["muted"]).pack(anchor="w", pady=(10, 0))

    tk.Button(body, text="Close",
              font=("Segoe UI", 10, "bold"),
              bg=C["indigo"], fg="white", relief="flat",
              cursor="hand2", padx=18, pady=7, bd=0,
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
            pystray.MenuItem("Disconnect & Re-pair", _tray_repair),
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
