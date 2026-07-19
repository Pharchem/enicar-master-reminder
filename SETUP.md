# SETUP — actions required before go-live (v3)

Everything below needs a human because it involves credentials, Google deployment, or
GMP judgement the system must not guess. **Nothing sends email until step 5 and an
explicit `DRY_RUN=false`.**

---

## 1. Create the Google Sheet (source of truth)

1. New Google Sheet: **"Enicar Master Reminder Register"**.
2. Import from `data/sheets/` (File → Import → Upload → *Insert new sheet(s)*):
   - `MASTER_consolidated.csv` → rename tab to **MASTER** (2,682 rows; the engine,
     dashboard, and Apps Script all use this tab)
   - `QA.csv` → **QA** (252) · `QC.csv` → **QC** (205) · `Micro.csv` → **Micro** (331) ·
     `Engineering.csv` → **Engineering** (1,894)  *(read-only convenience views for teams)*
   - `AuditLog.csv` → **AuditLog** (header only — the Apps Script appends here;
     never edit or delete audit rows)
3. Teams do **not** edit the Sheet — all ticks and reschedules go through the dashboard,
   which writes via the Apps Script and audit-logs every change.
4. Publish two tabs as CSV (File → Share → **Publish to web**):
   - **MASTER** → CSV → copy URL
   - **AuditLog** → CSV → copy URL

## 2. Wire the published URLs

- `config/config.yaml` → `sheet_csv_url:` (MASTER URL) and `audit_csv_url:` (AuditLog URL).
- `docs/config.js` → `SHEET_CSV_URL` and `AUDIT_CSV_URL` (same two URLs).

## 3. Deploy the Apps Script write-back web app

1. Open the Sheet → **Extensions → Apps Script**.
2. Delete the default code; paste the entire contents of `apps-script/Code.gs`.
3. **Deploy → New deployment → Web app**:
   - Description: `enicar-reminder-writeback`
   - Execute as: **Me** (your account — writes happen under your identity)
   - Who has access: **Anyone** (the dashboard has no login; the audit log records
     every change with an IST timestamp)
4. Authorize when prompted, copy the **web app URL** (ends `/exec`), and paste it into:
   - `config/config.yaml` → `apps_script_url:`
   - `docs/config.js` → `WRITEBACK_URL`
5. Sanity check: open `<web app URL>?action=health` in a browser — you should see
   `{"ok":true,...}`.
6. If you later edit Code.gs, use **Deploy → Manage deployments → Edit → New version**
   (a brand-new deployment changes the URL and you'd have to re-wire it).

## 4. Gmail app password → GitHub repo secrets

1. On the sending account (`info@pharchem.in`): enable 2-Step Verification, then create a
   16-character **App Password** (Google Account → Security → App passwords).
2. GitHub repo → Settings → Secrets and variables → Actions → New repository secret:
   - `MAIL_USERNAME` = `info@pharchem.in`
   - `MAIL_APP_PASSWORD` = the app password
3. Never commit credentials; `config.yaml` deliberately holds none.

Recipients are already configured in `config/config.yaml` (edit there if they change):
QA `qa@enicarpharma.com` · QC `qc@enicarpharma.com` · Micro `micro@enicarpharma.com` ·
Engineering `engineering@enicarpharma.com`; QA is CC'd on everything; ADMIN escalation CC =
`swaralisave@`, `mkverma@`, `nimishpatil@enicarpharma.com`.

## 5. Publish the dashboard + go live

1. Push `master-reminder-system/` to a GitHub repo; Settings → Pages → deploy branch
   folder `/master-reminder-system/docs` (or move `docs/` to repo root `/docs`).
2. The daily Action (`.github/workflows/daily-reminders.yml`, ~07:00 IST) starts in
   **DRY_RUN** — it writes would-be emails to `data/dry-run-logs/<date>.log` and commits
   them. Review a few days.
3. **Baseline sweep:** the first run sends (or in dry-run, logs) ONE consolidated email
   per department listing all open tasks, asking teams to tick off history on the
   dashboard. It is recorded in the sent-log and never repeats. Give teams a few days to
   clear the backlog before going live with the cadence.
4. Go live: run the workflow manually with `dry_run=false`, or change the workflow
   default to `false`.

---

## DECISIONS FOR YOU (surfaced by this build's simulations)

### A. Email volume — the backlog must be triaged, and batching is strongly recommended
The full-month simulation (`data/sim-reports/sim_2026-07-19_2026-08-18_pertask.txt`):
**14,969 emails in 31 days (~483/day), over the 10/day threshold on 30 of 31 days —
14,466 of those touches are `[CRITICAL]` escalations.** Cause: every past-2026 occurrence
was loaded with no action ticked, so the engine treats all of them as overdue (that also
means EVERY one of those emails would CC all three ADMIN addresses).

- The **baseline sweep + dashboard ticking** is the real fix — teams mark history done
  and the critical stream collapses to genuine misses.
- Until that happens, set **`batch_by_department: true`** in `config/config.yaml`:
  verified batched run = **124 emails/31 days, max 4/day, 0 days flagged**; a digest is
  marked `[CRITICAL]` + ADMIN CC only when it contains critical items.

Recommendation: launch with batching ON; consider per-task emails later only if the
open-task count stays small.

### B. Chase the missing planners (details in `intake-report.md`)
QA: vendor audit planner, APQR, compliance timelines. QC: control sample verification,
standard/reagent inventory renewals. Micro: media prep / growth-promotion cycles.
Engineering: confirm whether separate calibration/validation planners exist.

### C. Confirm ownership ("Assignments to confirm" in `intake-report.md`)
1. QA "Medical Checkup" (VMP Annexure 5) — HR/Admin instead of QA?
2. Engineering PM on QC-lab equipment (104 rows) — Engineering owns the reminders?
3. Shared-instrument calibration across QA/QC/Micro/Engineering — no gap or double-count.

### D. Correct the 6 excepted rows (`parse-exceptions.md`)
Five QA year-typo/blank due dates and one Micro autoclave without a next-due were NOT
registered. Fix the sources and re-run, or hand-enter corrected rows in the Sheet
(the Apps Script and engine will pick them up like any other row).

---

## Local test rig (no Google needed)

`python3 engine/mock_writeback.py --port 8747` serves the dashboard AND a faithful local
mock of the Apps Script (same actions, same audit semantics, against the local CSVs) at
`http://localhost:8747/index.html`. Ticks, reschedules, the watch list, and audit rows can
all be exercised before anything touches Google. This is how the write-back was verified.

## Re-running after new/corrected planners arrive
```bash
python3 data/parsed/<dept>_parse.py    # re-parse that department (emits v2 schema)
python3 engine/migrate_v3.py           # upgrade any v2-schema register to v3
python3 engine/consolidate.py          # rebuild MASTER + per-dept CSVs + dashboard snapshot
python3 engine/simulate.py --start <d1> --end <d2>   # re-check volume before re-import
```
Then re-import ONLY the new rows into the Sheet (never overwrite live done/audit data).
