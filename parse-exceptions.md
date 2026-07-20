# Parse Exceptions — consolidated

Reference date: 2026-07-15. One row per source line that could **not** be registered
confidently. Per the "never invent dates" rule, these were left out of the register
rather than guessed. Department teams should correct the source and re-run the parser
(or hand-enter the corrected row into the Google Sheet).

**Total excepted rows: 6** (QA 5, Micro 1, QC 0, Engineering 0).
Against 2,682 registered occurrences, that is a 99.8% clean-parse rate.

## QA — 5 exceptions

| # | Source file | Sheet | Row | Cell / content | Reason |
|---|-------------|-------|-----|----------------|--------|
| 1 | Year 2025-2026 Validation-calibration schedule-QA.xlsx | 2025-2026 | 31 | Due Date `03.06.206` (Refrigerator QCI/02018) | Year not 4 digits — almost certainly `03.06.2026`. Not auto-corrected. |
| 2 | Year 2025-2026 Validation-calibration schedule-QA.xlsx | 2025-2026 | 56 | Due Date `04.12.206` (Data logger DL 24–DL 35) | Year not 4 digits — likely `04.12.2026`. Not auto-corrected. |
| 3 | VMP 2026 (Annexure 1 to 7)-QA.xlsx | Annexure 3 | 9–11 | pH Meter Digital (QCI/02120) | "Due Date" label present but no date value beside it. |
| 4 | VMP 2026 (Annexure 1 to 7)-QA.xlsx | Annexure 3 | 57–59 | `28.09.206` (Measuring Scale S-01) | Year-typo due date. Likely `28.09.2026`. Not auto-corrected. |
| 5 | VMP 2026 (Annexure 1 to 7)-QA.xlsx | Annexure 3 | 119–121 | `03.06.206` (Heating Mantle) | Year-typo due date. Likely `03.06.2026`. Not auto-corrected. |

## Micro — 1 exception

| # | Source file | Sheet | Row | Cell / content | Reason |
|---|-------------|-------|-----|----------------|--------|
| 1 | Calibration & validation Planner_26_27_Micro.xls | Calibration Planner 26-27 | 32 | Destruction Autoclave (QCM/02033) — has "Calib. On" but no "Due On" date | No due date to register; last-done exists but next-due is blank. |

## QC — 0 exceptions (current-year data)

All dated cells in the current-year tabs (`3075_2026`, `4075_2026`) and the calibration
matrix parsed cleanly. Notes on items deliberately **not** registered (not errors):

- 5 yearly / outside-agency calibration items carry **no dated occurrence** in the matrix
  (Muffle Furnace QCI/02016; Stability Chambers QCI/02026 ×2, QCI/02027; Walk-in Chamber
  QCI/02092). No date exists to register — excluded, not invented.
- 2 secondary "Yearly (Outside agency)" chains (Vacuum Oven, Dry Oven) carry no dates; only
  their dated quarterly chains were registered.
- **Update 2026-07-19 (director instruction):** the prior-year stability tabs
  (`3075_2023/2024/2025`, `4075_2024/2025`) are now PARSED as well — they carry 12-M/18-M/
  24-M/36-M pulls falling due in 2026–27. This added 1,001 pull occurrences (QC total now
  1,206). Only pulls dated inside the window are registered; 3 unparseable `30.02.2024`
  dates in `3075_2023` are excepted (out-of-window either way). Existing task IDs were
  verified unchanged.

## Engineering — 0 exceptions

Every PM matrix cell was a real date with an extractable equipment ID inside the 2026 window.
Regex ID-extraction handled malformed parentheses (e.g. `UTL/04152` missing a close-paren)
without dropping any row.

## Data-quality flags for the teams (registered, but verify)

- **QC calibration due dates are month-level only** (the matrix marks a month, not a day), so
  all 100 QC calibration occurrences are `due_type=month_window` (first-of-month). The email
  engine treats them as month windows (5-touch cadence across the month). If QC actually
  performs these on specific days, add day-level dates to the planner.
- **QA VMP re-qualifications are mostly dated 2029** (five-yearly). Per the occurrence rule,
  only the single next occurrence is registered even though it is beyond the 12-month window.
