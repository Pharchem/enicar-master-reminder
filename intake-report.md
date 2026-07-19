# Intake Report — Enicar Recurring-Task Planners

Reference date: 2026-07-15. Files were delivered in four department folders
(`QA/`, `QC/`, `Micro/`, `Engineering/`) rather than a single `source-data/` folder —
same intake, department already labelled by folder.

## Files received (8 files, 50 sheets)

| Department | File | Sheets (non-empty) | Inferred planner | Registered rows |
|---|---|---|---|---|
| QA | Year 2025-2026 Validation-calibration schedule-QA.xlsx | 1 | Validation & calibration schedule (near 4-col schema) | 53 |
| QA | VMP 2026 (Annexure 1 to 7)-QA.xlsx | 7 | Validation Master Plan re-qualifications | 199 |
| QC | Calibration Planner_26_27_QC.xls | 1 (Sheet1) | Instrument calibration (month matrix) | 100 |
| QC | Stability_2026.xls | 2 current-year (3075_2026, 4075_2026) + 5 historical | Stability study planner | 105 |
| Micro | Calibration & validation Planner_26_27_Micro.xls | 2 (Calibration, Re-validation) | Instrument calibration + re-validation | 31 |
| Micro | EM Schedule-2026-Air Sampling Monitoring 2026.xlsx | 12 (monthly) | EM — active air sampling (high-frequency) | 108 |
| Micro | EM Schedule-2026-Settle Plate Monitoring 2026.xlsx | 12 (monthly) | EM — settle plate (high-frequency) | 192 |
| Engineering | Preventive Maintenance Planner 2026.xlsx | 9 (by area) | Preventive maintenance (month matrix) | 1,894 |

**Total registered occurrences: 2,682** (12-month window 2026-01-01 → 2027-07-31, plus
next-occurrence-only for five-yearly re-qualifications).

## Reconciliation against what was requested

### QA — requested: vendor audit planner, APQR, compliance timelines, validation & calibration planners
- **Received:** validation & calibration schedule; VMP annexures (validation/re-qualification).
- **MISSING — vendor audit planner.** Not in either file.
- **MISSING — APQR (Annual Product Reviews).** No product-review schedule present.
- **MISSING — compliance timelines.** No compliance-timeline planner. (VMP Annexure 5 has a
  lone "Medical Checkup" personnel item — not a compliance-timeline planner; see below.)

### QC — requested: control sample verification, standard/reagent inventory renewals, stability planner, instrument calibration
- **Received:** instrument calibration matrix; stability planner.
- **MISSING — control sample verification planner.** Not sent.
- **MISSING — standard / reagent inventory renewals.** Not sent.

### Micro — requested: environmental monitoring schedules, media preparation / growth promotion cycles
- **Received:** EM air-sampling schedule; EM settle-plate schedule; plus instrument
  calibration and a re-validation planner (extra, not requested but useful — folded in).
- **MISSING — media preparation / growth promotion (GPT) cycle planner.** No "media",
  "growth", or "promotion" content in any supplied Micro file.

### Engineering — requested: PM planners, equipment/instrument calibration, validation planners
- **Received:** preventive maintenance planner (9 areas, 297 instruments, 1,894 dated tasks).
- **PARTIAL — equipment/instrument calibration:** Engineering did not send a separate
  calibration planner. Equipment calibration for the plant appears to live in the QA
  Validation-calibration schedule and the QC/Micro calibration matrices. Confirm whether
  Engineering owns any calibration not already covered there.
- **MISSING — validation planners:** no Engineering-specific validation planner (plant/
  equipment qualification appears under the QA VMP annexures). Confirm ownership.

## Sent but not fitting the requested structure

- **Micro re-validation planner** — a second sheet in the Micro calibration file; not
  explicitly requested but clearly recurring, so registered as `planner_type = Validation`.
- **Engineering PM on QC-lab equipment** — the "PM Q.C.I. LAB" / "PM Q.C.M. LAB" sheets are
  PM performed by Engineering on QC lab instruments. Kept under Engineering (they perform it),
  with a remark. 104 rows. Confirm this is the intended owner for reminders.
- **QA "Medical Checkup" (VMP Annexure 5)** — a personnel/health item, registered under QA
  with a blank activity type. Likely belongs to HR/Admin — flagged under "Assignments to confirm."

## Assignments to confirm (no silent guessing on GMP data)

1. **QA "Medical Checkup"** (task_id `QA-VMP5-001-20270101`, due 2027-01-01): personnel/health
   item — confirm whether HR/Admin should own it and what its activity type is.
2. **Engineering PM on QC-lab equipment** (104 rows, "PM Q.C.I./Q.C.M. LAB" sheets): confirm
   Engineering is the reminder owner rather than QC.
3. **Equipment calibration ownership** between QA schedule, QC/Micro matrices, and Engineering —
   confirm there is no gap or double-count for shared plant instruments.

## Chase list (missing planners to collect before the system is complete)

| Department | Missing planner |
|---|---|
| QA | Vendor audit planner |
| QA | APQR (Annual Product Reviews) |
| QA | Compliance timelines |
| QC | Control sample verification planner |
| QC | Standard / reagent inventory renewals |
| Micro | Media preparation / growth promotion (GPT) cycle planner |
| Engineering | Confirm whether a separate equipment-calibration / validation planner exists |

When these arrive, drop them into the department folder and re-run the matching parser
(`data/parsed/<dept>_parse.py`), then re-consolidate — the register and dashboard pick up
the new rows automatically.
