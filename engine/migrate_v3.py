#!/usr/bin/env python3
"""
One-time migration: v2 register schema -> v3 schema.

v2: task_id..due_date, last_done_date, done_date, status, responsible_email,
    report_link, remarks, source_file
v3: adds report_due_date (= due_date + 10 days), splits done/status into
    action_done_date/action_status and report_done_date/report_status, adds
    rescheduled_from/reschedule_reason, and fills real department emails.

Idempotent: skips files already in v3 shape.
"""
from __future__ import annotations
import csv
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

V2 = ["task_id","department","planner_type","task_name","equipment_or_item_id",
      "activity_type","frequency","due_type","due_date","last_done_date","done_date",
      "status","responsible_email","report_link","remarks","source_file"]
V3 = ["task_id","department","planner_type","task_name","equipment_or_item_id",
      "activity_type","frequency","due_type","due_date","report_due_date",
      "last_done_date","action_done_date","action_status","report_done_date",
      "report_status","responsible_email","report_link","rescheduled_from",
      "reschedule_reason","remarks","source_file"]

DEPT_EMAIL = {
    "QA": "qa@enicarpharma.com",
    "QC": "qc@enicarpharma.com",
    "Micro": "micro@enicarpharma.com",
    "Engineering": "engineering@enicarpharma.com",
}


def report_due(due: str) -> str:
    d = datetime.strptime(due, "%Y-%m-%d") + timedelta(days=10)
    return d.strftime("%Y-%m-%d")


def migrate_file(path: Path) -> str:
    with open(path, newline="") as fh:
        r = csv.DictReader(fh)
        cols = r.fieldnames
        rows = [dict(x) for x in r]
    if cols == V3:
        return f"{path.name}: already v3 ({len(rows)} rows), skipped"
    if cols != V2:
        raise SystemExit(f"{path.name}: unexpected schema {cols}")
    out = []
    for x in rows:
        done = (x.get("done_date") or "").strip()
        out.append({
            "task_id": x["task_id"], "department": x["department"],
            "planner_type": x["planner_type"], "task_name": x["task_name"],
            "equipment_or_item_id": x["equipment_or_item_id"],
            "activity_type": x["activity_type"], "frequency": x["frequency"],
            "due_type": x["due_type"], "due_date": x["due_date"],
            "report_due_date": report_due(x["due_date"]),
            "last_done_date": x["last_done_date"],
            "action_done_date": done, "action_status": "done" if done else "pending",
            "report_done_date": "", "report_status": "pending",
            "responsible_email": DEPT_EMAIL.get(x["department"], x["responsible_email"]),
            "report_link": x["report_link"],
            "rescheduled_from": "", "reschedule_reason": "",
            "remarks": x["remarks"], "source_file": x["source_file"],
        })
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=V3)
        w.writeheader(); w.writerows(out)
    return f"{path.name}: migrated {len(out)} rows to v3"


def main():
    for f in sorted((ROOT / "data" / "parsed").glob("*_register.csv")):
        print(migrate_file(f))


if __name__ == "__main__":
    main()
