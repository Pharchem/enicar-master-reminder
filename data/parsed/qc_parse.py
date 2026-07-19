#!/usr/bin/env python3
"""
QC department planner parser -> canonical task register CSV.
Follows master-reminder-system/PARSING_SPEC.md exactly.
Reference date: 2026-07-15. Occurrence window: 2026-01-01 .. 2027-07-31.
"""
import os, re, csv, datetime
import xlrd
from xlrd import xldate_as_tuple

ROOT = "/Users/swarali/Desktop/Enicar/ENincar 2025-26 schedule"
OUT_CSV = os.path.join(ROOT, "master-reminder-system/data/parsed/qc_register.csv")
OUT_EXC = os.path.join(ROOT, "master-reminder-system/data/parsed/qc-exceptions.md")

WIN_START = datetime.date(2026, 1, 1)
WIN_END = datetime.date(2027, 7, 31)

COLUMNS = ["task_id","department","planner_type","task_name","equipment_or_item_id",
           "activity_type","frequency","due_type","due_date","last_done_date",
           "done_date","status","responsible_email","report_link","remarks","source_file"]

rows = []          # register rows (dicts)
exceptions = []    # dicts: source_file, sheet, row, cell, reason
notes = []         # assignments / info notes

def cell_date(sh, wb, r, c):
    """Return datetime.date from a date-typed cell, else None."""
    cell = sh.cell(r, c)
    if cell.ctype == 3:
        try:
            t = xldate_as_tuple(cell.value, wb.datemode)
            return datetime.date(t[0], t[1], t[2])
        except Exception:
            return None
    return None

def parse_ddmmyyyy(s):
    """Parse 'DD.MM.YYYY' string -> (date or None, reason_if_bad)."""
    s = str(s).strip()
    if not s:
        return None, "empty"
    m = re.match(r"^(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})$", s)
    if not m:
        return None, "unrecognized date format"
    dd, mm, yy = m.group(1), m.group(2), m.group(3)
    if len(yy) != 4:
        return None, "year not 4 digits (possible typo)"
    try:
        return datetime.date(int(yy), int(mm), int(dd)), None
    except ValueError as e:
        return None, "invalid calendar date (%s)" % e

def get_cell_date_any(sh, wb, r, c):
    """Return (date, raw_str, err). Handles both datetime cells and DD.MM.YYYY strings.
    Returns (None,'',None) for genuinely empty cells."""
    cell = sh.cell(r, c)
    if cell.ctype == 3:  # real date
        d = cell_date(sh, wb, r, c)
        if d:
            return d, d.isoformat(), None
        return None, str(cell.value), "unparseable datetime serial"
    raw = str(cell.value).strip()
    if raw == "":
        return None, "", None
    d, err = parse_ddmmyyyy(raw)
    return d, raw, err

# ---------------------------------------------------------------------------
# 1) CALIBRATION PLANNER
# ---------------------------------------------------------------------------
CAL_FILE = "QC/Calibration Planner_26_27_QC.xls"
FREQ_MAP = {"monthly":"monthly","quarterly":"quarterly","half yearly":"half-yearly",
            "halfyearly":"half-yearly","yearly":"yearly","annually":"yearly",
            "fortnightly":"fortnightly","weekly":"weekly","daily":"daily"}

def norm_freq(raw):
    key = re.sub(r"\s+", " ", str(raw)).strip().lower()
    return FREQ_MAP.get(key, "per-schedule")

wb = xlrd.open_workbook(os.path.join(ROOT, CAL_FILE))
sh = wb.sheet_by_name("Sheet1")

# Identify instrument blocks by Sr.No in col0 (data starts at row 2)
block_starts = []
for r in range(2, sh.nrows):
    v = str(sh.cell(r, 0).value).strip()
    if v:  # a Sr.No like "1.0"
        block_starts.append(r)
block_starts.append(sh.nrows)  # sentinel

for i in range(len(block_starts) - 1):
    start = block_starts[i]
    end = block_starts[i + 1]
    srno_raw = str(sh.cell(start, 0).value).strip()
    try:
        srno = int(float(srno_raw))
    except ValueError:
        srno = i + 1
    nnn = "%03d" % srno

    # Collect name text + frequency + agency across the block
    name_parts, id_found, agency = [], None, False
    freq_raw = str(sh.cell(start, 2).value).strip()
    for r in range(start, end):
        col1 = str(sh.cell(r, 1).value).strip()
        col2 = str(sh.cell(r, 2).value).strip()
        if col1:
            name_parts.append(col1)
        if "outside agency" in col2.lower():
            agency = True
        mid = re.search(r"(QCI/\d+)", col1)
        if mid and not id_found:
            id_found = mid.group(1)
    joined = " ".join(name_parts)
    mid = re.search(r"(QCI/\d+)", joined)
    if mid and not id_found:
        id_found = mid.group(1)
    equip_id = id_found or ""
    # clean display name: drop id parenthetical and stray parens
    disp = re.sub(r"\(?\s*QCI/\d+\s*\)?", "", joined)
    disp = re.sub(r"\s+", " ", disp).strip(" -").strip()

    freq = norm_freq(freq_raw)

    # Any dated cells in this block? Only on 'Due On' rows, months cols 4..15
    emitted_any = False
    for r in range(start, end):
        col3 = str(sh.cell(r, 3).value).strip().lower()
        if col3 != "due on":
            continue
        for c in range(4, 16):
            d = cell_date(sh, wb, r, c)
            if d is None:
                # if the cell has non-empty non-date content, flag it
                cv = sh.cell(r, c)
                if cv.ctype not in (0, 6) and str(cv.value).strip():
                    exceptions.append(dict(source_file=CAL_FILE, sheet="Sheet1",
                        row=r, cell="col%d=%r" % (c, cv.value),
                        reason="Non-date value in a Due On month cell for instrument %s" % disp))
                continue
            if not (WIN_START <= d <= WIN_END):
                continue
            due_iso = d.isoformat()
            remark = freq_raw + "; sheet Sheet1"
            if agency:
                remark += "; Outside agency"
            rows.append(dict(
                task_id="QC-CAL-%s-%s01" % (nnn, d.strftime("%Y%m")),
                department="QC",
                planner_type="Instrument Calibration",
                task_name="Calibrate %s" % disp,
                equipment_or_item_id=equip_id,
                activity_type="calibration",
                frequency=freq,
                due_type="month_window",
                due_date=due_iso,
                last_done_date="",  # no Calib. On dates present in this file
                done_date="",
                status="pending",
                responsible_email="QC_EMAIL",
                report_link="",
                remarks=remark,
                source_file=CAL_FILE,
            ))
            emitted_any = True
    if not emitted_any and agency:
        notes.append("Calibration Sr.No %s (%s / %s): Yearly, Outside agency, no dated "
                     "occurrence in the matrix - excluded (no date to register)." %
                     (srno_raw, disp or "?", equip_id or "no id"))

# ---------------------------------------------------------------------------
# 2) STABILITY STUDY PLANNER
# ---------------------------------------------------------------------------
STAB_FILE = "QC/Stability_2026.xls"
wbs = xlrd.open_workbook(os.path.join(ROOT, STAB_FILE))

STAB_TABS = {
    "3075_2026": {"type": "long-term",   "stations": ["3-M","6-M","9-M","12-M","18-M","24-M","36-M"]},
    "4075_2026": {"type": "accelerated", "stations": ["1-M","3-M","6-M"]},
}
# Historical tabs present but excluded:
HIST_TABS = [t for t in wbs.sheet_names() if t not in STAB_TABS]

nnn_counter = 0
for tab, meta in STAB_TABS.items():
    sh = wbs.sheet_by_name(tab)
    stations = meta["stations"]
    first_station_col = 6  # cols 0..5 are Sr,Name,Batch,Mfg,Exp,DateOfPlacement
    # header row index: find row containing 'Sr. No.'
    hdr = None
    for r in range(min(3, sh.nrows)):
        if "sr. no" in str(sh.cell(r, 0).value).strip().lower():
            hdr = r
            break
    if hdr is None:
        hdr = 0
    for r in range(hdr + 1, sh.nrows):
        srno_raw = str(sh.cell(r, 0).value).strip()
        name = str(sh.cell(r, 1).value).strip()
        if not srno_raw and not name:
            continue
        batch = str(sh.cell(r, 2).value).strip()
        nnn_counter += 1
        nnn = "%03d" % nnn_counter
        # Date of Placement -> last_done_date
        pd, praw, perr = get_cell_date_any(sh, wbs, r, 5)
        last_done = pd.isoformat() if pd else ""
        if praw and perr:
            exceptions.append(dict(source_file=STAB_FILE, sheet=tab, row=r,
                cell="Date of Placement=%r" % praw,
                reason="Unparseable placement date for %s batch %s: %s" % (name, batch, perr)))

        for k, station in enumerate(stations):
            col = first_station_col + k
            if col >= sh.ncols:
                break
            d, raw, err = get_cell_date_any(sh, wbs, r, col)
            if raw == "" and d is None and err is None:
                continue  # empty station
            if err:
                exceptions.append(dict(source_file=STAB_FILE, sheet=tab, row=r,
                    cell="%s=%r" % (station, raw),
                    reason="Unparseable pull date (%s) for %s batch %s; suggested reading: "
                           "verify DD.MM.YYYY" % (err, name, batch)))
                continue
            if d is None:
                continue
            if not (WIN_START <= d <= WIN_END):
                continue  # honor window
            remark = "STAB %s; sheet %s; station %s" % (meta["type"], tab, station)
            rows.append(dict(
                task_id="QC-STAB-%s-%s" % (nnn, d.strftime("%Y%m%d")),
                department="QC",
                planner_type="Stability Study",
                task_name="Stability pull %s - %s batch %s" % (station, name, batch),
                equipment_or_item_id=batch,
                activity_type="stability_pull",
                frequency="per-schedule",
                due_type="specific_date",
                due_date=d.isoformat(),
                last_done_date=last_done,
                done_date="",
                status="pending",
                responsible_email="QC_EMAIL",
                report_link="",
                remarks=remark,
                source_file=STAB_FILE,
            ))

# ---------------------------------------------------------------------------
# WRITE OUTPUTS
# ---------------------------------------------------------------------------
rows.sort(key=lambda x: (x["planner_type"], x["due_date"], x["task_id"]))
with open(OUT_CSV, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for row in rows:
        w.writerow(row)

with open(OUT_EXC, "w") as f:
    f.write("# QC Parsing Exceptions & Notes\n\n")
    f.write("Source planners: `%s`, `%s`\n" % (CAL_FILE, STAB_FILE))
    f.write("Reference date 2026-07-15. Window 2026-01-01 .. 2027-07-31.\n\n")

    f.write("## Excluded historical stability tabs\n\n")
    f.write("The following prior-year tabs exist in `%s` and were SKIPPED as historical "
            "data (not current-year studies):\n\n" % STAB_FILE)
    for t in HIST_TABS:
        f.write("- `%s`\n" % t)
    f.write("\n")

    f.write("## Unparseable / ambiguous rows\n\n")
    if exceptions:
        f.write("| source_file | sheet | row | cell | reason |\n")
        f.write("|---|---|---|---|---|\n")
        for e in exceptions:
            f.write("| %s | %s | %s | %s | %s |\n" % (
                e["source_file"], e["sheet"], e["row"],
                str(e["cell"]).replace("|", "\\|"),
                str(e["reason"]).replace("|", "\\|")))
    else:
        f.write("_None. All dated cells parsed cleanly._\n")
    f.write("\n")

    f.write("## Assignments to confirm / notes\n\n")
    if notes:
        for n in notes:
            f.write("- %s\n" % n)
    else:
        f.write("_No ownership ambiguities. All rows belong to QC._\n")
    f.write("\n")

# console summary
from collections import Counter
by_type = Counter(r["planner_type"] for r in rows)
print("register rows:", len(rows))
for k, v in by_type.items():
    print("  ", k, v)
print("exceptions:", len(exceptions))
print("notes:", len(notes))
print("historical tabs skipped:", HIST_TABS)
