# Enicar Master Reminder System (v3)

One centralised register + dashboard + daily email engine for every recurring compliance
task across **QA, QC, Micro, and Engineering**, with dashboard tick-off, reschedule-with-
reason, an immutable audit log, and escalation to ADMIN — so no calibration, validation,
EM round, PM, or stability pull is ever missed **or left unreported**. Static site +
GitHub Actions + one Google Apps Script web app; no servers, no databases.

## Layout
```
master-reminder-system/
├── SETUP.md                    ← human actions before go-live (READ FIRST)
├── intake-report.md            ← what each dept sent vs. expected; chase list
├── parse-exceptions.md         ← 6 unparseable rows (never guessed)
├── PARSING_SPEC.md             ← parser schema + v3 migration note
├── config/config.yaml          ← recipients, CC rules, cadence, URLs (no secrets)
├── apps-script/Code.gs         ← write-back web app (deploy per SETUP.md §3)
├── data/
│   ├── parsed/                 ← per-dept parsers + registers (v3 schema)
│   ├── sheets/                 ← MASTER_consolidated + per-dept + AuditLog CSVs (Sheet import)
│   ├── sim-reports/            ← volume simulations + scenario-demo.txt (cadence proof)
│   └── dry-run-logs/           ← dated would-be-email logs (dry-run)
├── engine/
│   ├── reminder_engine.py      ← v3 cadence/CC/escalation, IST, idempotent, fail-loud
│   ├── simulate.py             ← any date range → daily volume, critical counts, >10/day flags
│   ├── demo_scenarios.py       ← reproducible proof of all 8 cadence/CC scenarios
│   ├── consolidate.py          ← rebuild master CSVs from the 4 registers
│   ├── migrate_v3.py           ← upgrade v2-schema registers to v3
│   └── mock_writeback.py       ← local dashboard + Apps-Script mock (test rig)
├── sent-log/sent_log.csv       ← committed idempotency record
├── docs/                       ← GitHub Pages dashboard (index.html, config.js, snapshot)
└── .github/workflows/daily-reminders.yml   ← daily cron ~07:00 IST
```

## The register (2,682 occurrences, 21-column v3 schema)
Each row tracks the **action** (do the task → `action_done_date/action_status`) and the
**report** (file the record → `report_done_date/report_status`, due `report_due_date` =
due + 10 days; month-window tasks: month-end + 10). `rescheduled_from` +
`reschedule_reason` preserve the original date whenever a task is pushed.

| Dept | Rows | Mostly |
|---|---|---|
| Engineering | 1,894 | Preventive maintenance (297 instruments) |
| Micro | 331 | EM rounds (high-frequency) + calibration/re-validation |
| QA | 252 | Validation & calibration schedule + VMP re-qualifications |
| QC | 205 | Instrument calibration (month windows) + stability pulls |

## How completion works (GMP audit trail)
Teams tick **"action done"** / **"report done"** (optional link) or log a
**reschedule with reason** on the dashboard. Each action posts to the Apps Script, which
updates the MASTER tab and appends an **immutable AuditLog row** (IST timestamp, task,
action, old→new, reason). A task rescheduled **2+ times** is flagged on the director watch
list and in the audit log. Emails for a task stop the moment its report is ticked.

## Email cadence (v3)
- **Baseline sweep (one-time):** one consolidated email per department listing all open
  tasks — confirm history on the dashboard before the cadence starts (2026-07-20).
- **Specific-date:** planning (due−3) → start (due) → after due: `[CRITICAL]` every 3 days.
- **Month-window:** planning (1st−3) → start (1st) → in-month status nag every 3 days →
  after month-end: `[CRITICAL]` every 3 days.
- **High-frequency (EM):** single due-day email; overdue → `[CRITICAL]` every 3 days.
- **Report:** after action tick, chaser every 3 days; past `report_due_date` → `[CRITICAL]`.
- **CC:** qa@ on every email (except when QA is the recipient); ADMIN
  (swaralisave@/mkverma@/nimishpatil@) **only** on `[CRITICAL]`, which also sets
  X-Priority 1 / Importance high. FROM the director's address.
- Idempotent via committed sent-log; all dates IST; unreachable Sheet = loud failure.

## Quick start (everything local, nothing sends)
```bash
pip install -r requirements.txt
python3 engine/demo_scenarios.py                              # cadence & CC proof
python3 engine/simulate.py --start 2026-07-19 --end 2026-08-18            # volume
python3 engine/simulate.py --start 2026-07-19 --end 2026-08-18 --batched  # digest mode
python3 engine/mock_writeback.py --port 8747                  # dashboard + write-back rig
```

## ⚠️ Before launch
Simulation shows ~483 emails/day (96.6% `[CRITICAL]`, ADMIN CC'd on all of them) until the
task backlog is triaged via the baseline sweep — launch with `batch_by_department: true`
(≤4 digests/day, verified). Full reasoning and go-live steps in `SETUP.md`.
