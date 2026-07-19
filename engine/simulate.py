#!/usr/bin/env python3
"""
Simulate the reminder engine over a date range without sending anything.

Runs each day in [start, end] through the engine in dry-run mode against an
ISOLATED sent-log (so the simulation never touches the production sent-log and
idempotency still holds across the simulated days). Prints a per-day email-volume
table, flags any day exceeding the configured high-volume threshold, and writes a
combined report plus per-day dry-run logs.

Usage:
    python engine/simulate.py --start 2026-09-01 --end 2026-09-30
    python engine/simulate.py --start 2026-07-15 --end 2026-08-15 --batched
"""
from __future__ import annotations
import argparse, os, tempfile
from datetime import date, timedelta
from pathlib import Path

import reminder_engine as eng  # same directory

ROOT = eng.ROOT


def daterange(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--config", default=str(eng.DEFAULT_CONFIG))
    ap.add_argument("--batched", action="store_true",
                    help="Force department-digest batching for this simulation.")
    ap.add_argument("--out", default=str(ROOT / "data" / "sim-reports"))
    args = ap.parse_args()

    start = eng.parse_iso(args.start); end = eng.parse_iso(args.end)
    if not start or not end or end < start:
        raise SystemExit("Bad --start/--end range.")

    cfg = eng.load_config(Path(args.config))
    if args.batched:
        cfg["batch_by_department"] = True
    threshold = cfg.get("high_volume_daily_threshold", 10)

    outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)
    # isolated sent-log for this simulation
    tmp_sentlog = Path(tempfile.mkdtemp(prefix="sim_sentlog_")) / "sent_log.csv"

    # monkeypatch config load so run() uses our (possibly batched) cfg
    orig_load = eng.load_config
    eng.load_config = lambda *_a, **_k: cfg  # type: ignore

    os.environ["DRY_RUN"] = "true"
    rows_report = []
    total_msgs = total_touch = total_crit = 0
    flagged = []
    dept_totals: dict[str, int] = {}
    touch_totals: dict[str, int] = {}
    try:
        for d in daterange(start, end):
            s = eng.run(as_of=d, dry_run=True, config_path=Path(args.config),
                        sentlog_path=tmp_sentlog, quiet=True)
            msgs, touch, crit = s["messages"], s["fresh"], s.get("critical", 0)
            total_msgs += msgs; total_touch += touch; total_crit += crit
            for k, v in s["by_department"].items():
                dept_totals[k] = dept_totals.get(k, 0) + v
            for k, v in s["by_touch"].items():
                touch_totals[k] = touch_totals.get(k, 0) + v
            flag = "  <-- OVER THRESHOLD" if msgs > threshold else ""
            if msgs > threshold:
                flagged.append((d.isoformat(), msgs))
            rows_report.append(
                f"{d.isoformat()} ({d.strftime('%a')})  emails={msgs:4d}  touches={touch:4d}  "
                f"critical={crit:4d}  {s['by_department']}{flag}")
    finally:
        eng.load_config = orig_load  # type: ignore

    days = (end - start).days + 1
    mode = "DEPARTMENT-BATCHED" if cfg.get("batch_by_department") else "PER-TASK"
    header = [
        f"# Reminder simulation {start} .. {end}  ({days} days)",
        f"# Mode: {mode}   High-volume threshold: {threshold} emails/day",
        f"# Data source: {'Sheet' if not eng._is_placeholder(cfg.get('sheet_csv_url','')) else 'local fallback CSV'}",
        "",
        f"TOTAL emails: {total_msgs}   TOTAL touches: {total_touch}   "
        f"CRITICAL touches: {total_crit}   "
        f"avg/day: {total_msgs/days:.1f}   peak-day flagged: {len(flagged)}",
        f"By department (touches): {dept_totals}",
        f"By touch type: {touch_totals}",
        "",
    ]
    if flagged:
        header.append(f"DAYS OVER {threshold} EMAILS ({len(flagged)}):")
        header += [f"   {d}: {n} emails" for d, n in flagged]
        header.append("")
        header.append("RECOMMENDATION: volume exceeds the per-day threshold on the days above. "
                      "Enable batch_by_department (one digest per department per day) to cap "
                      "volume at <= 4 emails/day. Re-run this simulation with --batched to compare.")
    else:
        header.append(f"No day exceeds {threshold} emails. Per-task cadence is sustainable.")
    header.append("\n## Per-day detail\n")

    report = "\n".join(header + rows_report) + "\n"
    fname = outdir / f"sim_{start}_{end}_{'batched' if cfg.get('batch_by_department') else 'pertask'}.txt"
    fname.write_text(report)
    print(report)
    print(f"\nReport written: {fname}")


if __name__ == "__main__":
    main()
