#!/usr/bin/env python3
"""Bulk SMS dashboard.  Run: python -m uvicorn app:app --reload"""
import csv
import io
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

load_dotenv()
import providers

ROOT = Path(__file__).parent
RESULTS = ROOT / "results.csv"
FIELDS = ["ts", "phone", "status", "detail", "provider", "provider_id"]
SEND_DELAY = float(os.getenv("SEND_DELAY", "0.25"))

app = FastAPI(title="Bulk SMS")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
tpl = Jinja2Templates(directory=ROOT / "templates")

STATE = {"running": False, "total": 0, "sent": 0, "failed": 0, "log": []}
BAL = {"text": "—"}
_lock = threading.Lock()


def normalize_phone(raw: str) -> str:
    s = str(raw).strip()
    if not s:
        return ""
    d = re.sub(r"\D", "", s)
    if not d:
        return ""
    if s.startswith("+"):
        return "+" + d
    if d.startswith("00"):
        return "+" + d[2:]
    if len(d) == 10:
        return "+1" + d
    if len(d) == 11 and d[0] == "1":
        return "+" + d
    if len(d) == 11 and d[0] == "0":
        return "+234" + d[1:]
    return "+" + d


def refresh_balance():
    try:
        b = providers.current().balance()
        BAL["text"] = f"{b[1]} {b[0]:,.2f}" if b else "—"
    except Exception:
        BAL["text"] = "—"


def append_results(rows):
    with _lock:
        new = not RESULTS.exists()
        with RESULTS.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
            w.writerows(rows)


def read_results(limit=500):
    if not RESULTS.exists():
        return []
    with RESULTS.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))[-limit:][::-1]


def run_campaign(rows, template, brand):
    p = providers.current()
    STATE.update(running=True, total=len(rows), sent=0, failed=0, log=[])
    out = []
    for row in rows:
        if not STATE["running"]:
            break
        phone = normalize_phone(row.get("phone", ""))
        body = template.replace("{name}", row.get("name") or "there")
        if brand:
            body = f"{brand}: {body}"
        if not phone:
            res = providers.SendResult("", False, error="empty number")
        else:
            res = p.send(phone, body)
        entry = {"phone": phone or "(blank)", "status": res.status if res.ok else "failed",
                 "detail": res.error or "", "id": res.provider_id}
        STATE["log"].append(entry)
        STATE["sent" if res.ok else "failed"] += 1
        out.append({"ts": datetime.now().isoformat(timespec="seconds"), "phone": phone,
                    "status": entry["status"], "detail": entry["detail"],
                    "provider": p.name, "provider_id": res.provider_id})
        time.sleep(SEND_DELAY)
    append_results(out)
    STATE["running"] = False
    refresh_balance()


@app.on_event("startup")
def startup():
    refresh_balance()
    print(f"[startup] provider={providers.current().label}  balance={BAL['text']}")


def ctx(request, page, **kw):
    return {"request": request, "page": page, "balance": BAL["text"],
            "provider_label": providers.current().label, **kw}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return tpl.TemplateResponse(request, "index.html", ctx(request, "compose"))


@app.get("/history", response_class=HTMLResponse)
def history(request: Request):
    return tpl.TemplateResponse(request, "history.html", ctx(request, "history", rows=read_results()))


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    return tpl.TemplateResponse(request, "settings.html", ctx(
        request, "settings", providers=providers.available(),
        active=os.getenv("SMS_PROVIDER", "msgrush"), delay=SEND_DELAY,
        keys={k: bool(os.getenv(k)) for k in ("MSGRUSH_KEY", "SMSROUTE_KEY", "TEXTBELT_KEY")}))


@app.post("/settings")
def save_settings(provider: str = Form(...), delay: float = Form(0.25)):
    env = ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    seen = set()
    for i, ln in enumerate(lines):
        k = ln.split("=", 1)[0].strip()
        if k == "SMS_PROVIDER":
            lines[i] = f"SMS_PROVIDER={provider}"
            seen.add(k)
        elif k == "SEND_DELAY":
            lines[i] = f"SEND_DELAY={delay}"
            seen.add(k)
    for k, v in (("SMS_PROVIDER", provider), ("SEND_DELAY", delay)):
        if k not in seen:
            lines.append(f"{k}={v}")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ["SMS_PROVIDER"] = provider
    refresh_balance()
    return {"ok": True, "provider": provider}


@app.get("/api/config")
def api_config():
    p = providers.current()
    return {"provider": p.name, "provider_label": p.label, "per_sms": p.per_sms,
            "currency": p.currency, "balance": BAL["text"]}


@app.post("/api/refresh-balance")
def api_refresh():
    refresh_balance()
    return {"balance": BAL["text"]}


@app.post("/send")
async def send(file: UploadFile = File(None), message: str = Form(...),
               brand: str = Form(""), quick: str = Form("")):
    rows = []
    if file is not None and file.filename:
        raw = (await file.read()).decode("utf-8", errors="ignore")
        rows += [r for r in csv.DictReader(io.StringIO(raw)) if r.get("phone")]
    for n in re.split(r"[,\n;]+", quick):
        if n.strip():
            rows.append({"phone": n.strip(), "name": "there"})
    if not rows:
        return JSONResponse({"ok": False, "error": "Add a number or upload a CSV."}, status_code=400)
    if STATE["running"]:
        return JSONResponse({"ok": False, "error": "A campaign is already running."}, status_code=409)
    threading.Thread(target=run_campaign, args=(rows, message, brand.strip()), daemon=True).start()
    return {"ok": True, "count": len(rows)}


@app.post("/stop")
def stop():
    STATE["running"] = False
    return {"ok": True}


@app.get("/status")
def status():
    return JSONResponse(STATE)