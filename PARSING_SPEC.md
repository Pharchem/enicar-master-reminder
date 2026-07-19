# Canonical Task Register — Parsing Specification

Every department parser MUST emit a CSV with EXACTLY these columns, in this order:

```
task_id,department,planner_type,task_name,equipment_or_item_id,activity_type,frequency,due_type,due_date,last_done_date,done_date,status,responsible_email,report_link,remarks,source_file
```

## Field rules

- **task_id**: `{DEPT}-{PLANNER}-{NNN}-{YYYYMMDD}` where DEPT ∈ QA|QC|MIC|ENG, PLANNER is a
  short planner code (CAL, VAL, PM, EMAIR, EMSET, STAB, VMP1..VMP7, SCHED), NNN is a stable
  3-digit number for the underlying task (same base task keeps the same NNN across its
  occurrences), and YYYYMMDD is the due date (use YYYYMM01 for month windows).
  Example: `QC-CAL-005-20260601`.
- **department**: `QA`, `QC`, `Micro`, or `Engineering` (exact strings).
- **planner_type**: human phrase, e.g. `Instrument Calibration`, `Preventive Maintenance`,
  `EM - Air Sampling`, `EM - Settle Plate`, `Stability Study`, `Equipment Re-qualification`,
  `Validation`, `Temperature Mapping`.
- **task_name**: plain-language task, e.g. `Calibrate FTIR`, `PM - Boiler`,
  `Stability pull 6-M - CYPRO B PLUS batch GE93238`, `EM air sampling - Microbiology Section`.
- **equipment_or_item_id**: the ID in the sheet, e.g. `QCI/02052`, `UTL/04058`, batch no. for
  stability, format no. for EM. Empty if none.
- **activity_type**: `calibration`, `preventive_maintenance`, `re-qualification`, `validation`,
  `temperature_mapping`, `environmental_monitoring`, `stability_pull`, `media_gpt`, etc.
- **frequency**: normalized token: `daily|weekly|fortnightly|monthly|quarterly|half-yearly|yearly|two-yearly|five-yearly|one-time|per-schedule`. For combined codes like `M/Q/HY` use the SMALLEST interval (that is what the dated cells encode) and put the raw code in remarks.
- **due_type**: `specific_date` when the source gives a day; `month_window` when the source
  only marks a month (put first-of-month in due_date).
- **due_date**: ISO `YYYY-MM-DD`. NEVER invent a date. If a cell is unparseable, the row goes
  to the exceptions file, not the register.
- **last_done_date**: ISO date if the sheet records the last performed date (e.g. `Calib. On`,
  `Perfrom Date`, `Date of Placement`). Else empty.
- **done_date / report_link**: always empty at intake (teams will fill in the Sheet).
- **status**: `pending` for every generated occurrence (even past-due ones — overdue is
  computed, not stored). Use `done` ONLY if the source explicitly marks completion with a date.
- **responsible_email**: placeholder token: `QA_EMAIL`, `QC_EMAIL`, `MICRO_EMAIL`, `ENG_EMAIL`.
- **remarks**: raw frequency code, agency (e.g. `Outside agency`), source sheet name, and any
  parsing caveat. Keep short. No commas problems — CSV-quote properly.
- **source_file**: path relative to project root, e.g. `QC/Calibration Planner_26_27_QC.xls`.

## Occurrence-generation window

- Include EVERY occurrence with a due date from **2026-01-01** through **2027-07-31**
  (past-due 2026 rows are wanted — the overdue engine needs them).
- Five-yearly / two-yearly items: include ONLY the next occurrence, even if beyond the window.
- If the sheet lists explicit future dates (stability pulls, EM schedules, PM matrix), use the
  sheet's dates verbatim — do NOT generate from frequency. Frequency-based generation is only
  for 4-column-schema files that give frequency + last-done/next-due with no explicit calendar.
- High-frequency flag: EM schedules (per-day rows) keep one row per scheduled date, but append
  `HIGH_FREQ` at the start of remarks so the email engine applies single-email cadence.

## Never guess

- Unparseable/ambiguous rows → `{dept}-exceptions.md` with source file, sheet, row number,
  cell content, and the reason.
- Data-quality problems you can safely interpret (e.g. obvious year typo `03.06.206`) → do NOT
  silently fix; put the row in exceptions with your suggested reading.
- Tasks whose owning department is unclear → include in a `## Assignments to confirm` section
  of your notes file, and still register them under your department with remarks
  `OWNERSHIP-UNCONFIRMED`.

## v3 note

Parsers emit the original (v2) 16-column schema above; `engine/migrate_v3.py` upgrades a
register in place to the live v3 schema (adds report_due_date = due+10 — month-window
tasks: month-end+10 — splits done/status into action_*/report_*, adds rescheduled_from /
reschedule_reason, and fills real department emails). Always run migrate_v3.py then
engine/consolidate.py after re-parsing.
