#!/usr/bin/env python3
"""
Parse QA_SOP/SOP INDEX.xlsx into the canonical (v2) register schema.

Each SOP/SCP/CAL row across all 8 department sheets becomes ONE "SOP Review" task,
due on its REVIEW DATE, routed to its owning department. Multi-block sheets
(QC/STORE/ENGINEERING have SOP + SCP + CAL columns side by side) are all read.

Emits v2 schema; run engine/migrate_v3.py then engine/consolidate.py afterwards.
"""
from __future__ import annotations
import csv, re
from datetime import datetime
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]   # the schedule dir (holds QA_SOP/, QC/, ...)
SRC = "QA_SOP/SOP INDEX.xlsx"
OUT = Path(__file__).resolve().parent / "sop_register.csv"
EXC = Path(__file__).resolve().parent / "sop-exceptions.md"

COLUMNS = ["task_id","department","planner_type","task_name","equipment_or_item_id",
           "activity_type","frequency","due_type","due_date","last_done_date","done_date",
           "status","responsible_email","report_link","remarks","source_file"]

SHEET_DEPT = {
    "QA": "QA", "QC": "QC", "MICRO": "Micro", "PRODUCTION": "Production",
    "STORE": "Store", "ENGINEERING": "Engineering", "PA-EHS": "PA-EHS", "RA": "RA",
}
EMAIL_TOKEN = {  # legacy responsible_email token; engine routes via config department_emails
    "QA": "QA_EMAIL", "QC": "QC_EMAIL", "Micro": "MICRO_EMAIL", "Engineering": "ENG_EMAIL",
    "Production": "PRODUCTION_EMAIL", "Store": "STORE_EMAIL",
    "PA-EHS": "PAEHS_EMAIL", "RA": "RA_EMAIL",
}


def parse_date(v):
    """Return (iso, error). Accepts datetime or DD.MM.YYYY / DD-MM-YYYY strings."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None, None
    if isinstance(v, datetime):
        return v.date().isoformat(), None
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return None, None
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date().isoformat(), None
        except ValueError:
            continue
    return None, f"unparseable date {s!r}"


def infer_freq(issue_iso, review_iso):
    if not issue_iso or not review_iso:
        return "per-schedule"
    d0 = datetime.fromisoformat(issue_iso); d1 = datetime.fromisoformat(review_iso)
    yrs = round((d1 - d0).days / 365.25)
    return {1: "yearly", 2: "two-yearly", 3: "three-yearly"}.get(yrs, "per-schedule")


def main():
    xl = pd.ExcelFile(ROOT / SRC)
    rows, exceptions = [], []
    seen_ids = {}
    for sheet in xl.sheet_names:
        dept = SHEET_DEPT.get(sheet.strip().upper()) or SHEET_DEPT.get(sheet.strip())
        if not dept:
            exceptions.append((sheet, "-", "-", f"unknown sheet -> no department mapping"))
            continue
        df = xl.parse(sheet, header=None)
        # locate header row
        hdr = None
        for i in range(min(4, len(df))):
            if any("review date" in str(v).strip().lower() for v in df.iloc[i]):
                hdr = i; break
        if hdr is None:
            exceptions.append((sheet, "-", "-", "no header row with REVIEW DATE")); continue
        header = [str(v).strip() for v in df.iloc[hdr]]
        # each id-block: an ID column (SOP/SCP/CAL No), with TITLE just left and the
        # ISSUE/REVIEW DATE columns to its right (before the next block)
        blocks = []
        for j, h in enumerate(header):
            if re.search(r"(SOP|SCP|CAL)\s*No", h, re.I):
                rd = next((k for k, hh in enumerate(header) if "review date" in hh.lower() and k >= j), None)
                iss = next((k for k, hh in enumerate(header) if "issue date" in hh.lower() and k >= j), None)
                title = next((k for k in range(j - 1, -1, -1) if "title" in header[k].lower()), j - 1)
                blocks.append((j, title, iss, rd))
        for idc, titlec, issc, rdc in blocks:
            if rdc is None:
                continue
            for i in range(hdr + 1, len(df)):
                sopno = str(df.iat[i, idc]).strip()
                if not sopno or sopno.lower() == "nan" or "-" not in sopno:
                    continue
                title = str(df.iat[i, titlec]).strip() if titlec is not None else ""
                title = "" if title.lower() == "nan" else title
                review_iso, rerr = parse_date(df.iat[i, rdc])
                issue_iso, _ = parse_date(df.iat[i, issc]) if issc is not None else (None, None)
                if rerr or not review_iso:
                    exceptions.append((sheet, sopno, str(df.iat[i, rdc]),
                                       rerr or "missing REVIEW DATE")); continue
                ymd = review_iso.replace("-", "")
                tid = f"{sopno}-{ymd}"
                if tid in seen_ids:      # keep unique if a SOP repeats
                    seen_ids[tid] += 1; tid = f"{tid}-{seen_ids[tid]}"
                else:
                    seen_ids[tid] = 0
                rev = str(df.iat[i, idc - 1]).strip() if idc - 1 >= 0 else ""
                rows.append({
                    "task_id": tid, "department": dept, "planner_type": "SOP Review",
                    "task_name": f"Review {sopno}" + (f" - {title}" if title else ""),
                    "equipment_or_item_id": sopno, "activity_type": "sop_review",
                    "frequency": infer_freq(issue_iso, review_iso),
                    "due_type": "specific_date", "due_date": review_iso,
                    "last_done_date": issue_iso or "", "done_date": "", "status": "pending",
                    "responsible_email": EMAIL_TOKEN[dept], "report_link": "",
                    "remarks": f"SOP INDEX sheet {sheet}; issued {issue_iso or '?'}",
                    "source_file": SRC,
                })

    rows.sort(key=lambda r: (r["department"], r["due_date"], r["task_id"]))
    with open(OUT, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS); w.writeheader(); w.writerows(rows)

    from collections import Counter
    by_dept = Counter(r["department"] for r in rows)
    with open(EXC, "w") as fh:
        fh.write("# SOP INDEX — parsing exceptions & summary\n\n")
        fh.write(f"Parsed {len(rows)} SOP-review tasks from `{SRC}`.\n\n")
        fh.write("By department: " + ", ".join(f"{k} {v}" for k, v in sorted(by_dept.items())) + "\n\n")
        fh.write("## Exceptions (rows skipped)\n\n")
        if exceptions:
            fh.write("| sheet | SOP No | cell | reason |\n|---|---|---|---|\n")
            for s, n, c, r in exceptions:
                fh.write(f"| {s} | {n} | {str(c)[:20]} | {r} |\n")
        else:
            fh.write("_None — every row with a REVIEW DATE parsed cleanly._\n")

    print(f"SOP tasks: {len(rows)}  | by dept: {dict(sorted(by_dept.items()))}")
    print(f"exceptions: {len(exceptions)}")


if __name__ == "__main__":
    main()
