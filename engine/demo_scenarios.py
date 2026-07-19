#!/usr/bin/env python3
"""
Scenario demo: proves the v3 cadence, CC and escalation rules on a tiny synthetic
register, printing every generated email in full (TO / CC / priority / subject / body).

Covers:
  1. One-time baseline sweep (one consolidated email per department, CC qa@,
     no qa@ duplication when QA is the recipient; never repeats).
  2. Normal specific-date task: planning (due-3) and start (due-day) emails.
  3. Overdue task, action not ticked -> [CRITICAL] + ADMIN CC + high-priority header,
     repeating every 3 days.
  4. Action ticked, report overdue -> [CRITICAL] report chaser + ADMIN CC.
  5. Rescheduled task: cadence follows the NEW due date; the email carries the
     original date + reason; no emails on the old date.
  6. Month-window task: in-month status nag is NORMAL (no ADMIN), post-month critical.
  7. High-frequency task: single due-day reminder, then critical stream.
  8. Report ticked -> total silence.

Run: python3 engine/demo_scenarios.py
"""
from __future__ import annotations
import csv, tempfile
from datetime import date
from pathlib import Path

import reminder_engine as eng

ROOT = eng.ROOT
V3 = ["task_id","department","planner_type","task_name","equipment_or_item_id",
      "activity_type","frequency","due_type","due_date","report_due_date",
      "last_done_date","action_done_date","action_status","report_done_date",
      "report_status","responsible_email","report_link","rescheduled_from",
      "reschedule_reason","remarks","source_file"]


def row(**kw):
    base = {c: "" for c in V3}
    base.update(action_status="pending", report_status="pending", source_file="demo")
    base.update(kw)
    return base


TASKS = [
    # 2: normal specific-date task due 25 Jul
    row(task_id="DEMO-NORMAL", department="QC", planner_type="Instrument Calibration",
        task_name="Calibrate FTIR", equipment_or_item_id="QCI/02052",
        activity_type="calibration", frequency="monthly", due_type="specific_date",
        due_date="2026-07-25", report_due_date="2026-08-04"),
    # 3: action overdue since 10 Jul -> critical stream
    row(task_id="DEMO-OVERDUE", department="Engineering", planner_type="Preventive Maintenance",
        task_name="PM - Boiler", equipment_or_item_id="UTL/04058",
        activity_type="preventive_maintenance", frequency="monthly", due_type="specific_date",
        due_date="2026-07-10", report_due_date="2026-07-20"),
    # 4: action done 12 Jul, report overdue (report_due 20 Jul)
    row(task_id="DEMO-REPORT-OD", department="Micro", planner_type="Validation",
        task_name="Re-validate Sterilization Autoclave", equipment_or_item_id="QCM/02030",
        activity_type="re-validation", frequency="yearly", due_type="specific_date",
        due_date="2026-07-10", report_due_date="2026-07-20",
        action_done_date="2026-07-12", action_status="done"),
    # 5: rescheduled from 15 Jul to 28 Jul with reason
    row(task_id="DEMO-RESCHED", department="QA", planner_type="Validation & Calibration Schedule",
        task_name="Temperature mapping - Solvent area", equipment_or_item_id="",
        activity_type="temperature_mapping", frequency="yearly", due_type="specific_date",
        due_date="2026-07-28", report_due_date="2026-08-07",
        rescheduled_from="2026-07-15", reschedule_reason="Mapping probes with vendor for repair"),
    # 6: month-window task for August
    row(task_id="DEMO-MONTHWIN", department="QC", planner_type="Instrument Calibration",
        task_name="Calibrate Refractometer", equipment_or_item_id="QCI/02004",
        activity_type="calibration", frequency="quarterly", due_type="month_window",
        due_date="2026-08-01", report_due_date="2026-09-10"),
    # 7: high-frequency EM round due 22 Jul
    row(task_id="DEMO-HIGHFREQ", department="Micro", planner_type="EM - Settle Plate",
        task_name="EM settle plate - Micro section", equipment_or_item_id="128/01",
        activity_type="environmental_monitoring", frequency="per-schedule",
        due_type="specific_date", due_date="2026-07-22", report_due_date="2026-08-01",
        remarks="HIGH_FREQ"),
    # 8: fully closed task -> must be silent forever
    row(task_id="DEMO-CLOSED", department="QA", planner_type="Validation & Calibration Schedule",
        task_name="Calibrate hygrometers DTH-01..16", equipment_or_item_id="DTH-01",
        activity_type="calibration", frequency="yearly", due_type="specific_date",
        due_date="2026-07-01", report_due_date="2026-07-11",
        action_done_date="2026-07-01", action_status="done",
        report_done_date="2026-07-05", report_status="done"),
]

DAYS = ["2026-07-19",  # before cadence start: baseline sweep ONLY
        "2026-07-20",  # cadence start; baseline NOT repeated; nothing on the 3-day grids
        "2026-07-22",  # planning for DEMO-NORMAL (due-3); high-freq due-day
        "2026-07-24",  # report chaser grid (action done 07-12 -> +12d) past report_due -> CRITICAL
        "2026-07-25",  # start for DEMO-NORMAL; resched planning (28-3); high-freq critical
        "2026-08-04",  # month-window: in-month status nag (NORMAL, no ADMIN CC)
        ]


def main():
    tmp = Path(tempfile.mkdtemp(prefix="demo_"))
    reg = tmp / "register.csv"
    with open(reg, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=V3); w.writeheader(); w.writerows(TASKS)

    cfg = eng.load_config()
    cfg["local_fallback_csv"] = str(reg)
    cfg["batch_by_department"] = False
    orig = eng.load_config
    eng.load_config = lambda *a, **k: cfg
    sentlog = tmp / "sent_log.csv"
    logdir = ROOT / "data" / "dry-run-logs"
    try:
        for d in DAYS:
            y, m, dd = map(int, d.split("-"))
            eng.run(as_of=date(y, m, dd), dry_run=True, sentlog_path=sentlog, quiet=True)
            log = logdir / f"{d}.log"
            print("=" * 88)
            print(f"### {d}")
            print(log.read_text())
    finally:
        eng.load_config = orig


if __name__ == "__main__":
    main()
