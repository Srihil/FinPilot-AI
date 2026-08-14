"""
FinPilot Tally Connector — System Tray App
==========================================
Runs as a Windows system tray application.
Background threads handle heartbeat and job polling.
GUI thread manages the tray icon and pairing window.
"""
import socket
import sys
import threading
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import font as tkfont
from typing import Optional

# ── Imports with visible error on failure ─────────────────────────────────────
try:
    import httpx
    import pystray
    from PIL import Image, ImageDraw
    from config import config, BASE_DIR
    from tally_client import TallyClient, TallyError
except Exception as e:
    import tkinter as tk
    root = tk.Tk(); root.withdraw()
    import tkinter.messagebox as mb
    mb.showerror("FinPilot Connector — Startup Error", f"{type(e).__name__}: {e}\n\n{traceback.format_exc()}")
    sys.exit(1)

FINPILOT_URL = "https://finpilot-frontend-vbdf.onrender.com/tally"
ENV_FILE = BASE_DIR / ".env"

# ── State ─────────────────────────────────────────────────────────────────────
_state = {
    "connected": False,
    "tally_online": False,
    "company": "",
    "error": "",
}
_tray_icon: Optional[pystray.Icon] = None
_stop_event = threading.Event()


# ── Env helpers ───────────────────────────────────────────────────────────────

def _save_env(key: str, value: str) -> None:
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = [l for l in content.splitlines() if not l.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ── Tray icon drawing ─────────────────────────────────────────────────────────

def _make_icon(connected: bool, tally_online: bool) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background circle
    bg = (34, 197, 94) if (connected and tally_online) else \
         (251, 191, 36) if connected else (100, 116, 139)
    d.ellipse([4, 4, size - 4, size - 4], fill=bg)

    # White "F" letter
    d.text((22, 16), "FP", fill=(255, 255, 255))

    # Small status dot bottom-right
    dot = (34, 197, 94) if tally_online else (239, 68, 68)
    d.ellipse([44, 44, 60, 60], fill=dot, outline=(255, 255, 255), width=2)
    return img


def _update_tray() -> None:
    if _tray_icon is None:
        return
    connected = _state["connected"]
    tally_on = _state["tally_online"]
    company = _state["company"]

    if connected and tally_on:
        title = f"FinPilot ● Connected — {company}" if company else "FinPilot ● Connected"
    elif connected:
        title = "FinPilot ◌ Connector active — TallyPrime offline"
    else:
        title = "FinPilot ○ Not connected"

    _tray_icon.icon = _make_icon(connected, tally_on)
    _tray_icon.title = title


# ── Cloud API ─────────────────────────────────────────────────────────────────

def _headers() -> dict:
    return {"Authorization": f"Bearer {config.CONNECTOR_TOKEN}",
            "Content-Type": "application/json"}


def _api(path: str) -> str:
    return config.FINPILOT_API_URL.rstrip("/") + path


def _pair(code: str) -> str:
    payload = {
        "pairing_code": code.strip().upper(),
        "connector_name": "FinPilot Connector",
        "device_name": socket.gethostname(),
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(_api("/api/tally/connector/register"), json=payload,
                           headers={"Content-Type": "application/json"})
        if resp.status_code == 400:
            raise ValueError(resp.json().get("detail", "Invalid pairing code"))
        resp.raise_for_status()
        data = resp.json()
    token = data["token"]
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
    payload = {"tally_reachable": reachable, "tally_company_name": company,
               "tally_host": config.TALLY_HOST, "tally_port": config.TALLY_PORT}
    with httpx.Client(timeout=10) as client:
        client.post(_api("/api/tally/connector/heartbeat"), json=payload, headers=_headers())
    _update_tray()


def _poll_and_run(tally: TallyClient) -> None:
    from connector import execute_job  # reuse existing logic
    with httpx.Client(timeout=15) as client:
        resp = client.get(_api("/api/tally/connector/jobs"), headers=_headers())
        resp.raise_for_status()
        jobs = resp.json().get("jobs", [])
    for job in jobs:
        result, error = execute_job(tally, job)
        payload = {"status": "SUCCESS" if error is None else "FAILED"}
        if result:
            payload["result"] = result
        if error:
            payload["error_message"] = error
        with httpx.Client(timeout=15) as client:
            client.post(_api(f"/api/tally/connector/jobs/{job['id']}/result"),
                        json=payload, headers=_headers())


# ── Background worker thread ──────────────────────────────────────────────────

def _worker() -> None:
    tally = TallyClient(host=config.TALLY_HOST, port=config.TALLY_PORT)
    last_hb = 0.0

    while not _stop_event.is_set():
        try:
            now = time.time()
            if now - last_hb >= config.HEARTBEAT_INTERVAL_SECONDS:
                _heartbeat(tally)
                last_hb = now
            _poll_and_run(tally)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                _state["connected"] = False
                _state["error"] = "Token revoked — please re-pair"
                _update_tray()
        except Exception:
            pass
        _stop_event.wait(config.POLL_INTERVAL_SECONDS)


# ── Pairing window (Tkinter) ──────────────────────────────────────────────────

def _show_pairing_window(on_success=None) -> None:
    win = tk.Tk()
    win.title("FinPilot — Connect TallyPrime")
    win.resizable(False, False)
    win.configure(bg="#f8fafc")

    # Center on screen
    win.update_idletasks()
    w, h = 420, 380
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.lift()
    win.focus_force()

    # ── Header ──
    header = tk.Frame(win, bg="#4f46e5", height=70)
    header.pack(fill="x")
    header.pack_propagate(False)
    tk.Label(header, text="⚡  FinPilot Tally Connector",
             font=("Segoe UI", 14, "bold"), fg="white", bg="#4f46e5").pack(expand=True)

    body = tk.Frame(win, bg="#f8fafc", padx=30, pady=20)
    body.pack(fill="both", expand=True)

    tk.Label(body, text="Connect your TallyPrime to FinPilot AI",
             font=("Segoe UI", 11), bg="#f8fafc", fg="#1e293b").pack(anchor="w")

    tk.Label(body, text="\nSteps:", font=("Segoe UI", 9, "bold"),
             bg="#f8fafc", fg="#475569").pack(anchor="w")
    steps = [
        "1. Open FinPilot in your browser",
        "2. Go to TallyPrime page",
        "3. Click 'Connect TallyPrime'",
        "4. Paste the pairing code below",
    ]
    for s in steps:
        tk.Label(body, text=s, font=("Segoe UI", 9),
                 bg="#f8fafc", fg="#64748b").pack(anchor="w")

    # Open browser button
    tk.Button(body, text="🌐  Open FinPilot →",
              font=("Segoe UI", 9), bg="#e0e7ff", fg="#4f46e5",
              relief="flat", cursor="hand2", padx=8, pady=4,
              command=lambda: webbrowser.open(FINPILOT_URL)
              ).pack(anchor="w", pady=(8, 0))

    tk.Label(body, text="\nPairing Code", font=("Segoe UI", 9, "bold"),
             bg="#f8fafc", fg="#475569").pack(anchor="w")

    code_var = tk.StringVar()
    code_entry = tk.Entry(body, textvariable=code_var, font=("Courier New", 14, "bold"),
                          width=16, relief="solid", bd=1, fg="#1e293b",
                          justify="center")
    code_entry.pack(anchor="w", ipady=6, pady=(2, 0))
    code_entry.focus_set()

    status_var = tk.StringVar(value="")
    status_lbl = tk.Label(body, textvariable=status_var, font=("Segoe UI", 9),
                          bg="#f8fafc", fg="#ef4444", wraplength=340, justify="left")
    status_lbl.pack(anchor="w", pady=(4, 0))

    btn_frame = tk.Frame(body, bg="#f8fafc")
    btn_frame.pack(fill="x", pady=(12, 0))

    def _do_pair():
        code = code_var.get().strip()
        if not code:
            status_var.set("Please enter the pairing code.")
            return
        connect_btn.config(state="disabled", text="Connecting...")
        status_var.set("")
        win.update()

        def _try():
            try:
                _pair(code)
                _state["connected"] = True
                _state["error"] = ""
                win.after(0, _on_paired)
            except ValueError as e:
                win.after(0, lambda: (
                    status_var.set(f"❌  {e}"),
                    connect_btn.config(state="normal", text="Connect"),
                ))
            except Exception as e:
                win.after(0, lambda: (
                    status_var.set(f"❌  Network error: {e}"),
                    connect_btn.config(state="normal", text="Connect"),
                ))

        threading.Thread(target=_try, daemon=True).start()

    def _on_paired():
        # Clear body and show success
        for w in body.winfo_children():
            w.destroy()
        tk.Label(body, text="✅  Connected!", font=("Segoe UI", 18, "bold"),
                 bg="#f8fafc", fg="#16a34a").pack(pady=(20, 4))
        tk.Label(body, text="TallyPrime is now linked to FinPilot AI.",
                 font=("Segoe UI", 10), bg="#f8fafc", fg="#475569").pack()
        tk.Label(body, text="The connector is running in your system tray.",
                 font=("Segoe UI", 10), bg="#f8fafc", fg="#475569").pack()

        _update_tray()
        if on_success:
            threading.Thread(target=on_success, daemon=True).start()

        tk.Button(body, text="Close this window",
                  font=("Segoe UI", 10), bg="#4f46e5", fg="white",
                  relief="flat", cursor="hand2", padx=12, pady=6,
                  command=win.destroy).pack(pady=20)

    connect_btn = tk.Button(btn_frame, text="Connect",
                            font=("Segoe UI", 10, "bold"),
                            bg="#4f46e5", fg="white", relief="flat",
                            cursor="hand2", padx=16, pady=8,
                            command=_do_pair)
    connect_btn.pack(side="left")

    win.bind("<Return>", lambda e: _do_pair())
    win.mainloop()


# ── Success / already-connected window ────────────────────────────────────────

def _show_status_window() -> None:
    win = tk.Tk()
    win.title("FinPilot Connector")
    win.resizable(False, False)
    win.configure(bg="#f8fafc")
    w, h = 360, 260
    x = (win.winfo_screenwidth() - w) // 2
    y = (win.winfo_screenheight() - h) // 2
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.lift(); win.focus_force()

    header = tk.Frame(win, bg="#4f46e5", height=60)
    header.pack(fill="x"); header.pack_propagate(False)
    tk.Label(header, text="⚡  FinPilot Tally Connector",
             font=("Segoe UI", 13, "bold"), fg="white", bg="#4f46e5").pack(expand=True)

    body = tk.Frame(win, bg="#f8fafc", padx=30, pady=20)
    body.pack(fill="both", expand=True)

    dot = "🟢" if (_state["connected"] and _state["tally_online"]) else "🟡" if _state["connected"] else "🔴"
    company = _state["company"] or "detecting..."
    tk.Label(body, text=f"{dot}  Connected", font=("Segoe UI", 14, "bold"),
             bg="#f8fafc", fg="#1e293b").pack(anchor="w")
    tk.Label(body, text=f"Company:  {company}",
             font=("Segoe UI", 10), bg="#f8fafc", fg="#475569").pack(anchor="w", pady=(4, 0))
    tk.Label(body, text=f"Tally:      {config.TALLY_HOST}:{config.TALLY_PORT}",
             font=("Segoe UI", 10), bg="#f8fafc", fg="#475569").pack(anchor="w")
    tk.Label(body, text="\nConnector is running in the system tray.\nYou can safely close this window.",
             font=("Segoe UI", 9), bg="#f8fafc", fg="#64748b").pack(anchor="w")

    tk.Button(body, text="Close", font=("Segoe UI", 10, "bold"),
              bg="#4f46e5", fg="white", relief="flat", cursor="hand2",
              padx=16, pady=6, command=win.destroy).pack(pady=(16, 0))

    webbrowser.open(FINPILOT_URL)
    win.mainloop()


# ── Tray menu actions ─────────────────────────────────────────────────────────

def _on_open_status(icon, item):
    threading.Thread(target=_show_status_window, daemon=True).start()


def _on_open_finpilot(icon, item):
    webbrowser.open(FINPILOT_URL)


def _on_disconnect(icon, item):
    _save_env("CONNECTOR_TOKEN", "")
    config.CONNECTOR_TOKEN = ""
    _state["connected"] = False
    _state["tally_online"] = False
    _state["company"] = ""
    _update_tray()
    threading.Thread(target=lambda: _show_pairing_window(
        on_success=lambda: _state.update({"connected": True})
    ), daemon=True).start()


def _on_exit(icon, item):
    _stop_event.set()
    icon.stop()
    sys.exit(0)


def _build_menu() -> pystray.Menu:
    return pystray.Menu(
        pystray.MenuItem("Status", _on_open_status, default=True),
        pystray.MenuItem("Open FinPilot", _on_open_finpilot),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Disconnect & Re-pair", _on_disconnect),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Exit", _on_exit),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    global _tray_icon

    # First-run pairing
    if not config.CONNECTOR_TOKEN:
        def _after_pair():
            _state["connected"] = True
            _worker_thread = threading.Thread(target=_worker, daemon=True)
            _worker_thread.start()

        _show_pairing_window(on_success=_after_pair)
        if not config.CONNECTOR_TOKEN:
            sys.exit(0)
    else:
        _state["connected"] = True
        worker = threading.Thread(target=_worker, daemon=True)
        worker.start()
        # Brief status window on launch
        threading.Thread(target=_show_status_window, daemon=True).start()

    # Build and run tray icon
    icon_img = _make_icon(False, False)
    _tray_icon = pystray.Icon(
        "finpilot-connector",
        icon_img,
        "FinPilot Connector",
        menu=_build_menu(),
    )
    _update_tray()
    _tray_icon.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import tkinter.messagebox as mb
        root = tk.Tk(); root.withdraw()
        mb.showerror("FinPilot Connector", f"Unexpected error:\n\n{traceback.format_exc()}")
        sys.exit(1)
