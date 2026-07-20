# QC Parsing Exceptions & Notes

Source planners: `QC/Calibration Planner_26_27_QC.xls`, `QC/Stability_2026.xls`
Reference date 2026-07-15. Window 2026-01-01 .. 2027-07-31.

## Stability tabs coverage

ALL study tabs in `QC/Stability_2026.xls` are parsed (2026 + prior-year studies): `3075_2026`, `4075_2026`, `3075_2025`, `4075_2025`, `3075_2024`, `4075_2024`, `3075_2023`. Only pull dates inside the window are registered; earlier pulls from historical studies are assumed already performed and are not tracked.

## Unparseable / ambiguous rows

| source_file | sheet | row | cell | reason |
|---|---|---|---|---|
| QC/Stability_2026.xls | 3075_2023 | 38 | 9-M='30.02.2024' | Unparseable pull date (invalid calendar date (day 30 must be in range 1..29 for month 2 in year 2024)) for TUSPEL PLUS EXPECTORANT batch 23CH0064; suggested reading: verify DD.MM.YYYY |
| QC/Stability_2026.xls | 3075_2023 | 39 | 9-M='30.02.2024' | Unparseable pull date (invalid calendar date (day 30 must be in range 1..29 for month 2 in year 2024)) for TUSPEL LS batch 23CH0072; suggested reading: verify DD.MM.YYYY |
| QC/Stability_2026.xls | 3075_2023 | 40 | 9-M='30.02.2024' | Unparseable pull date (invalid calendar date (day 30 must be in range 1..29 for month 2 in year 2024)) for TUSPEL LS batch 23CH0009; suggested reading: verify DD.MM.YYYY |

## Assignments to confirm / notes

- Calibration Sr.No 17.0 (Muffle Furnance / QCI/02016): Yearly, Outside agency, no dated occurrence in the matrix - excluded (no date to register).
- Calibration Sr.No 20.0 (Stability Chamber (30°C/75%RH) / QCI/02026): Yearly, Outside agency, no dated occurrence in the matrix - excluded (no date to register).
- Calibration Sr.No 21.0 (Stability Chamber (40°C/75%RH) / QCI/02026): Yearly, Outside agency, no dated occurrence in the matrix - excluded (no date to register).
- Calibration Sr.No 22.0 (Stability Chamber (40°C/75%RH) / QCI/02027): Yearly, Outside agency, no dated occurrence in the matrix - excluded (no date to register).
- Calibration Sr.No 23.0 (Walk In Type Stability Chamber (30°C/75%RH) / QCI/02092): Yearly, Outside agency, no dated occurrence in the matrix - excluded (no date to register).


## Missing planners (requested from QC, not received)

- **Control sample verification planner** — MISSING (not sent).
- **Standard / reagent inventory renewals** — MISSING (not sent).

QC sent only the instrument calibration matrix and the stability planner.
