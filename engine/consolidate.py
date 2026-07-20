#!/usr/bin/env python3
"""
Consolidate the four department registers into the master + per-department CSVs
and refresh the dashboard snapshot. Re-run after any parser re-runs.

    python engine/consolidate.py
"""
from __future__ import annotations
import csv, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ["task_id","department","planner_type","task_name","equipment_or_item_id",
        "activity_type","frequency","due_type","due_date","report_due_date",
        "last_done_date","action_done_date","action_status","report_done_date",
        "report_status","responsible_email","report_link","rescheduled_from",
        "reschedule_reason","remarks","source_file"]
DEPTS = ["QA","QC","Micro","Engineering"]
AUDIT_HEADER = ["timestamp_ist","task_id","department","action","field",
                "old_value","new_value","reason","source","operator"]


def main():
    parsed = ROOT / "data" / "parsed"
    files = sorted(parsed.glob("*_register.csv"))
    if not files:
        raise SystemExit(f"No *_register.csv found in {parsed}")
    rows = []
    for f in files:
        with open(f, newline="") as fh:
            r = csv.DictReader(fh)
            if r.fieldnames != SPEC:
                raise SystemExit(f"SCHEMA MISMATCH in {f.name}: {r.fieldnames}")
            rows.extend(dict(x) for x in r)

    # uniqueness + validity checks
    ids = [x["task_id"] for x in rows]
    if len(ids) != len(set(ids)):
        dupes = {i for i in ids if ids.count(i) > 1}
        raise SystemExit(f"Duplicate task_ids: {list(dupes)[:10]}")
    rows.sort(key=lambda x: (x["department"], x["due_date"], x["task_id"]))

    out = ROOT / "data" / "sheets"
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "MASTER_consolidated.csv", rows)
    for dep in DEPTS:
        _write(out / f"{dep}.csv", [x for x in rows if x["department"] == dep])
    # refresh dashboard snapshot
    _write(ROOT / "docs" / "MASTER_consolidated.csv", rows)

    # audit-log tab template (header only — audit rows are append-only, written by
    # the Apps Script web app; never regenerate over a live audit log)
    audit = out / "AuditLog.csv"
    if not audit.exists():
        with open(audit, "w", newline="") as fh:
            csv.writer(fh).writerow(AUDIT_HEADER)

    print(f"Consolidated {len(rows)} rows from {len(files)} registers.")
    for dep in DEPTS:
        print(f"  {dep:12} {sum(1 for x in rows if x['department']==dep)}")


def _write(path: Path, rows: list[dict]):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SPEC)
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
