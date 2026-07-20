#!/usr/bin/env python3
"""
Local mock of the Apps Script write-back web app, for testing the dashboard's
tick/reschedule flow WITHOUT a deployed Google endpoint. Mirrors apps-script/Code.gs:
same actions, same field updates, same append-only audit semantics — but against
the local CSVs (docs/MASTER_consolidated.csv and data/sheets/AuditLog.csv).

Also serves the docs/ directory, so one process gives you dashboard + write-back:

    python3 engine/mock_writeback.py --port 8747
    open http://localhost:8747/index.html

This is a TEST harness only. In production the dashboard posts to the deployed
Apps Script URL and the Google Sheet is the source of truth.
"""
from __future__ import annotations
import argparse, csv, json, calendar
from datetime import datetime, date, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
MASTER = ROOT / "docs" / "MASTER_consolidated.csv"
AUDIT = ROOT / "data" / "sheets" / "AuditLog.csv"
TZ = ZoneInfo("Asia/Kolkata")
AUDIT_HEADER = ["timestamp_ist","task_id","department","action","field",
                "old_value","new_value","reason","source","operator"]

# TEST-ONLY passwords for the local mock (production uses Apps Script Script Properties).
MOCK_PWD = {"QA":"qa123","QC":"qc123","Micro":"micro123","Engineering":"eng123"}
MOCK_ADMIN = "admin123"

def _verify_login(login, pwd):
    if not login or not pwd: return {"ok": False, "error": "login_required"}
    if MOCK_ADMIN and pwd == MOCK_ADMIN: return {"ok": True, "admin": True, "dept": login}
    if login not in MOCK_PWD: return {"ok": False, "error": "bad_login"}
    if MOCK_PWD[login] == "" or pwd != MOCK_PWD[login]: return {"ok": False, "error": "bad_password"}
    return {"ok": True, "dept": login}

def _check_auth(params, task_dept):
    login = params.get("dept_login", [""])[0].strip()
    pwd = params.get("pwd", [""])[0]
    operator = params.get("operator", [""])[0].strip()
    if not login or not pwd: return {"ok": False, "error": "login_required"}
    if not operator: return {"ok": False, "error": "operator_required"}
    if MOCK_ADMIN and pwd == MOCK_ADMIN: return {"ok": True, "operator": operator}
    if login not in MOCK_PWD: return {"ok": False, "error": "bad_login"}
    if MOCK_PWD[login] == "" or pwd != MOCK_PWD[login]: return {"ok": False, "error": "bad_password"}
    if task_dept and task_dept != login: return {"ok": False, "error": "wrong_department"}
    return {"ok": True, "operator": operator}


def now_ist() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S")


def today_ist() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def report_due(due_iso: str, due_type: str) -> str:
    y, m, d = map(int, due_iso.split("-"))
    if due_type == "month_window":
        base = date(y, m, calendar.monthrange(y, m)[1])
    else:
        base = date(y, m, d)
    return (base + timedelta(days=10)).isoformat()


def audit(task_id, dept, action, field, old, new, reason, source, operator=""):
    new_file = not AUDIT.exists()
    with open(AUDIT, "a", newline="") as fh:
        w = csv.writer(fh)
        if new_file:
            w.writerow(AUDIT_HEADER)
        w.writerow([now_ist(), task_id, dept, action, field, old, new, reason, source, operator])


def reschedule_count(task_id) -> int:
    if not AUDIT.exists():
        return 0
    with open(AUDIT, newline="") as fh:
        return sum(1 for r in csv.DictReader(fh)
                   if r["task_id"] == task_id and r["action"] == "reschedule")


def handle(params: dict) -> dict:
    action = params.get("action", [""])[0]
    task_id = params.get("task_id", [""])[0].strip()
    if action == "health":
        return {"ok": True, "service": "mock-writeback", "time_ist": now_ist()}
    if action == "verify_pwd":
        return _verify_login(params.get("dept_login", [""])[0].strip(),
                             params.get("pwd", [""])[0])
    if not task_id:
        return {"ok": False, "error": "task_id required"}

    with open(MASTER, newline="") as fh:
        r = csv.DictReader(fh)
        cols = r.fieldnames
        rows = [dict(x) for x in r]
    hit = next((x for x in rows if x["task_id"] == task_id), None)
    if hit is None:
        return {"ok": False, "error": f"task_id not found: {task_id}"}
    dept = hit["department"]
    today = today_ist()

    MUTATING = {"tick_action","tick_report","untick_action","untick_report","reschedule"}
    operator = ""
    if action in MUTATING:
        auth = _check_auth(params, dept)
        if not auth["ok"]:
            return {"ok": False, "error": "auth:" + auth["error"]}
        operator = auth["operator"]

    if action == "tick_action":
        if hit["action_status"].lower() == "done":
            return {"ok": True, "noop": True, "message": "action already done"}
        hit["action_done_date"] = today
        hit["action_status"] = "done"
        audit(task_id, dept, "tick_action", "action_status", "pending", "done", "", "dashboard", operator)
    elif action == "tick_report":
        if hit["report_status"].lower() == "done":
            return {"ok": True, "noop": True, "message": "report already done"}
        link = params.get("report_link", [""])[0].strip()
        hit["report_done_date"] = today
        hit["report_status"] = "done"
        if link:
            hit["report_link"] = link
        audit(task_id, dept, "tick_report", "report_status", "pending",
              "done" + (f" ({link})" if link else ""), "", "dashboard", operator)
    elif action == "untick_action":
        if hit["action_status"].lower() != "done":
            return {"ok": True, "noop": True, "message": "action is not marked done"}
        if hit["report_status"].lower() == "done":
            return {"ok": False, "error": "report is marked done — undo the report first"}
        reason = params.get("reason", [""])[0].strip()
        hit["action_done_date"] = ""
        hit["action_status"] = "pending"
        audit(task_id, dept, "untick_action", "action_status", "done", "pending", reason, "dashboard", operator)
    elif action == "untick_report":
        if hit["report_status"].lower() != "done":
            return {"ok": True, "noop": True, "message": "report is not marked done"}
        reason = params.get("reason", [""])[0].strip()
        hit["report_done_date"] = ""
        hit["report_status"] = "pending"
        audit(task_id, dept, "untick_report", "report_status", "done", "pending", reason, "dashboard", operator)
    elif action == "reschedule":
        new_due = params.get("new_due_date", [""])[0].strip()
        reason = params.get("reason", [""])[0].strip()
        if len(new_due) != 10:
            return {"ok": False, "error": "new_due_date must be YYYY-MM-DD"}
        if not reason:
            return {"ok": False, "error": "a reason is required to reschedule"}
        old_due = hit["due_date"]
        if not hit["rescheduled_from"]:
            hit["rescheduled_from"] = old_due     # preserve ORIGINAL forever
        hit["due_date"] = new_due
        hit["reschedule_reason"] = reason
        hit["report_due_date"] = report_due(new_due, hit["due_type"])
        audit(task_id, dept, "reschedule", "due_date", old_due, new_due, reason, "dashboard", operator)
        n = reschedule_count(task_id)
        if n >= 2:
            audit(task_id, dept, "reschedule_flag", "reschedule_count", str(n-1), str(n),
                  f"task rescheduled {n} times — director attention", "system", operator)
        with open(MASTER, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
        return {"ok": True, "task_id": task_id, "due_date": new_due, "reschedule_count": n}
    else:
        return {"ok": False, "error": f"unknown action: {action}"}

    with open(MASTER, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows)
    return {"ok": True, "task_id": task_id, "date": today}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "docs"), **kw)

    def do_POST(self):
        if not self.path.startswith("/writeback"):
            self.send_error(404); return
        length = int(self.headers.get("Content-Length", 0))
        params = parse_qs(self.rfile.read(length).decode())
        result = handle(params)
        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/audit.csv"):
            body = AUDIT.read_bytes() if AUDIT.exists() else (",".join(AUDIT_HEADER)+"\n").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/csv")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/writeback"):
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            result = handle(parse_qs(qs))
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *a):  # quiet
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8747)
    args = ap.parse_args()
    print(f"Mock write-back + dashboard on http://localhost:{args.port}/ "
          f"(endpoint http://localhost:{args.port}/writeback)")
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
