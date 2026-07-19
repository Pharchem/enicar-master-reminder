#!/usr/bin/env python3
"""
Enicar Master Reminder System — email engine (v3).

Reads the task register (published Google Sheet CSV; local fallback in dry-run only),
computes the reminder "touches" due on a given IST date, and either logs them
(DRY_RUN, the default) or sends via Gmail SMTP.

Guarantees:
  * All date math in IST (Asia/Kolkata).
  * Idempotent: committed sent-log keyed by (date, task_id, touch_type);
    re-runs never double-send. The one-time baseline sweep is keyed the same way.
  * Fail-loud: in live mode an unreachable Sheet aborts the run with a non-zero
    exit — it never reports success having sent nothing.

Cadence (v3) — per task, driven by action_status / report_status ticks
----------------------------------------------------------------------
Everything stops the moment report_status = done.

BASELINE (one-time, before the cadence starts): one consolidated email per
department listing all open tasks, asking the team to confirm completions on the
dashboard. Sent once ever (sent-log key BASELINE-<dept>).

Normal cadence runs only from cadence_start_date (2026-07-20) onward.

Specific-date task, action not ticked:
    due-3  planning | due  start | after due: every 3 days [CRITICAL]+ADMIN
Month-window task (due_date = 1st, window = whole month), action not ticked:
    (1st-3d) planning | 1st start | in-month every 3 days: status nag (normal)
    | after month-end: every 3 days [CRITICAL]+ADMIN
High-frequency task (HIGH_FREQ remark), action not ticked:
    due-day single reminder | after due: every 3 days [CRITICAL]+ADMIN
Action ticked, report not ticked (any type):
    every 3 days report-chaser (anchored on action_done_date); becomes
    [CRITICAL]+ADMIN once report_due_date has passed.

Rescheduled tasks carry an updated due_date/report_due_date in the Sheet (written
by the Apps Script), so the cadence and escalation automatically follow the new
dates. rescheduled_from preserves the original date for the record.

CC rules:
    qa@ is CC'd on every email (skipped when QA is the recipient).
    ADMIN addresses are CC'd only on [CRITICAL] emails, which also carry
    X-Priority: 1 / Importance: high headers.
"""
from __future__ import annotations
import argparse, csv, io, os, sys, smtplib, ssl
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import yaml
except ImportError:
    print("PyYAML is required (pip install pyyaml).", file=sys.stderr); raise

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "config.yaml"
PLACEHOLDER_TOKENS = ("PASTE_", "_HERE")
DEPTS = ["QA", "QC", "Micro", "Engineering"]


# --------------------------------------------------------------------------- #
# Config & data loading
# --------------------------------------------------------------------------- #
def load_config(path: Path = DEFAULT_CONFIG) -> dict:
    with open(path) as fh:
        return yaml.safe_load(fh)


def _is_placeholder(v) -> bool:
    return v is None or any(tok in str(v) for tok in PLACEHOLDER_TOKENS)


def load_rows(cfg: dict, dry_run: bool) -> list[dict]:
    url = cfg.get("sheet_csv_url", "")
    if not _is_placeholder(url):
        import requests
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001 — must fail loudly
            raise SystemExit(f"FATAL: task Sheet unreachable ({exc}). Aborting; nothing sent.")
        text = resp.text
    else:
        if not dry_run:
            raise SystemExit(
                "FATAL: sheet_csv_url is not configured but DRY_RUN=false. "
                "Refusing to run live against a missing data source.")
        fallback = ROOT / cfg.get("local_fallback_csv", "data/sheets/MASTER_consolidated.csv")
        if not fallback.exists():
            raise SystemExit(f"FATAL: local fallback CSV not found at {fallback}.")
        text = fallback.read_text()
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise SystemExit("FATAL: task source returned zero rows. Aborting; nothing sent.")
    return rows


# --------------------------------------------------------------------------- #
# Date helpers (all IST)
# --------------------------------------------------------------------------- #
def today_ist(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def parse_iso(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def last_day_of_month(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    return date(d.year, d.month + 1, 1) - timedelta(days=1)


def every_n_after(today: date, anchor: date, n: int) -> bool:
    """True when `today` is anchor+n, anchor+2n, ... (strictly after anchor)."""
    delta = (today - anchor).days
    return delta > 0 and delta % n == 0


# --------------------------------------------------------------------------- #
# Touch model
# --------------------------------------------------------------------------- #
@dataclass
class Touch:
    task_id: str
    touch_type: str      # baseline|planning|start|status_nag|high_freq|
                         # action_critical|report_chaser|report_critical
    critical: bool
    subject: str
    body: str
    department: str
    row: dict = field(repr=False, default_factory=dict)


def is_high_freq(row: dict) -> bool:
    return (row.get("remarks") or "").startswith("HIGH_FREQ")


def action_done(row: dict) -> bool:
    return (row.get("action_status") or "").strip().lower() == "done"


def report_done(row: dict) -> bool:
    return (row.get("report_status") or "").strip().lower() == "done"


def _fmt(row: dict) -> dict:
    return {
        "task": (row.get("task_name") or "").strip() or "(unnamed task)",
        "eid": (row.get("equipment_or_item_id") or "").strip(),
        "act": (row.get("activity_type") or "").replace("_", " ").strip(),
        "dept": (row.get("department") or "").strip(),
        "due": (row.get("due_date") or "").strip(),
        "rdue": (row.get("report_due_date") or "").strip(),
    }


def _eid(f: dict) -> str:
    return f" (ID {f['eid']})" if f["eid"] else ""


def _resched_note(row: dict) -> str:
    orig = (row.get("rescheduled_from") or "").strip()
    if not orig:
        return ""
    reason = (row.get("reschedule_reason") or "").strip()
    return (f" NOTE: this task was rescheduled from {orig}"
            + (f" (reason: {reason})" if reason else "") + ".")


def compute_touches_for_row(row: dict, today: date, nag_n: int) -> list[Touch]:
    """Touches firing for one task row on `today` (normal cadence only —
    the baseline sweep is computed separately)."""
    if report_done(row):
        return []                       # fully closed: emails stop
    due = parse_iso(row.get("due_date", ""))
    if due is None:
        return []
    f = _fmt(row)
    tid = row["task_id"]
    rn = _resched_note(row)
    out: list[Touch] = []

    def mk(ttype, critical, subject, body):
        out.append(Touch(tid, ttype, critical, subject, body, f["dept"], row))

    # ---------------- report stream (action ticked, report pending) -----------
    if action_done(row):
        rdue = parse_iso(row.get("report_due_date", "")) or (due + timedelta(days=10))
        anchor = parse_iso(row.get("action_done_date", "")) or rdue
        overdue_report = today > rdue
        if every_n_after(today, anchor, nag_n):
            if overdue_report:
                n = (today - rdue).days
                mk("report_critical", True,
                   f"[CRITICAL] Report overdue {n}d: {f['task']}{_eid(f)}",
                   f"The report for {f['act']} {f['task']}{_eid(f)} ({f['dept']}) is OVERDUE "
                   f"by {n} day(s) — it was due {f['rdue']} (action completed "
                   f"{row.get('action_done_date','').strip() or 'earlier'}). Upload the report and tick "
                   f"'report completed' on the dashboard today.{rn}")
            else:
                mk("report_chaser", False,
                   f"[REPORT] {f['task']}{_eid(f)} — report due {f['rdue']}",
                   f"Action for {f['act']} {f['task']}{_eid(f)} ({f['dept']}) is complete; the "
                   f"report is still pending and is due {f['rdue']}. Upload it and tick "
                   f"'report completed' on the dashboard.{rn}")
        return out

    # ---------------- action stream (action not ticked) ------------------------
    if is_high_freq(row):
        if today == due:
            mk("high_freq", False,
               f"[TODAY] {f['task']}{_eid(f)} — perform today",
               f"Scheduled {f['act']} today ({f['due']}): {f['task']}{_eid(f)} ({f['dept']}). "
               f"Perform it, then tick 'action completed' on the dashboard.{rn}")
        elif every_n_after(today, due, nag_n):
            n = (today - due).days
            mk("action_critical", True,
               f"[CRITICAL] Overdue {n}d: {f['task']}{_eid(f)}",
               f"{f['act']} {f['task']}{_eid(f)} ({f['dept']}) was due {f['due']} and is "
               f"OVERDUE by {n} day(s) with no completion ticked. Perform it now and tick "
               f"'action completed', or log a reschedule with reason on the dashboard.{rn}")
        return out

    if row.get("due_type") == "month_window":
        first = date(due.year, due.month, 1)
        eom = last_day_of_month(first)
        month_name = first.strftime("%B %Y")
        if today == first - timedelta(days=3):
            mk("planning", False,
               f"[PLANNING] {f['task']}{_eid(f)} — due in {month_name}",
               f"{f['act'].capitalize()} {f['task']}{_eid(f)} ({f['dept']}) is due in "
               f"{month_name}. Plan it now; the window opens on the 1st. Report due "
               f"{f['rdue']}.{rn}")
        elif today == first:
            mk("start", False,
               f"[START] {f['task']}{_eid(f)} — {month_name} window open",
               f"The {month_name} window is open for {f['act']} {f['task']}{_eid(f)} "
               f"({f['dept']}). Begin now; tick 'action completed' on the dashboard when done. "
               f"Report due {f['rdue']}.{rn}")
        elif today <= eom and every_n_after(today, first, nag_n):
            mk("status_nag", False,
               f"[STATUS] {f['task']}{_eid(f)} — what's the status?",
               f"Status check: {f['act']} {f['task']}{_eid(f)} ({f['dept']}) is due within "
               f"{month_name} and is not yet ticked complete. Update the dashboard — or "
               f"reschedule with a reason if it genuinely cannot be done this month.{rn}")
        elif today > eom and every_n_after(today, eom, nag_n):
            n = (today - eom).days
            mk("action_critical", True,
               f"[CRITICAL] Overdue {n}d: {f['task']}{_eid(f)} — {month_name} window missed",
               f"{f['act'].capitalize()} {f['task']}{_eid(f)} ({f['dept']}) was due in "
               f"{month_name} and is OVERDUE by {n} day(s) with no completion ticked. "
               f"Complete it now and tick the dashboard, or log a reschedule with reason.{rn}")
        return out

    # specific_date
    if today == due - timedelta(days=3):
        mk("planning", False,
           f"[PLANNING] {f['task']}{_eid(f)} — due {f['due']}",
           f"{f['act'].capitalize()} {f['task']}{_eid(f)} ({f['dept']}) is due in 3 days, on "
           f"{f['due']}. Plan it now. Report due {f['rdue']}.{rn}")
    elif today == due:
        mk("start", False,
           f"[DUE TODAY] {f['task']}{_eid(f)}",
           f"Due today ({f['due']}): {f['act']} {f['task']}{_eid(f)} ({f['dept']}). Perform it "
           f"and tick 'action completed' on the dashboard. Report due {f['rdue']}.{rn}")
    elif every_n_after(today, due, nag_n):
        n = (today - due).days
        mk("action_critical", True,
           f"[CRITICAL] Overdue {n}d: {f['task']}{_eid(f)}",
           f"{f['act'].capitalize()} {f['task']}{_eid(f)} ({f['dept']}) was due {f['due']} and "
           f"is OVERDUE by {n} day(s) with no completion ticked. Complete it now and tick the "
           f"dashboard, or log a reschedule with reason.{rn}")
    return out


# --------------------------------------------------------------------------- #
# Baseline sweep (one-time)
# --------------------------------------------------------------------------- #
def baseline_touches(rows: list[dict], seen: set, cadence_start: date) -> list[Touch]:
    """One consolidated email per department listing all open tasks. Keyed
    BASELINE-<dept> in the sent-log so it can only ever fire once."""
    out = []
    for dept in DEPTS:
        key_id = f"BASELINE-{dept}"
        if any(k[1] == key_id for k in seen):
            continue
        open_rows = [r for r in rows if r.get("department") == dept and not report_done(r)]
        if not open_rows:
            continue
        open_rows.sort(key=lambda r: r.get("due_date", ""))
        lines = []
        for r in open_rows:
            f = _fmt(r)
            state = "action+report pending" if not action_done(r) else "report pending"
            lines.append(f"  - {r['task_id']} | {f['task']}{_eid(f)} | due {f['due']} | {state}")
        body = (
            f"Team {dept},\n\n"
            f"We are moving all recurring compliance tasks to the Master Reminder Dashboard. "
            f"Below are ALL {len(open_rows)} of your currently open task occurrences from the "
            f"register. Many were completed before this system existed — please go through the "
            f"dashboard and tick 'action completed' (and 'report completed' where the report "
            f"is filed) for everything already done, so reminders start from a clean state.\n\n"
            f"Anything left unticked will enter the reminder and escalation cadence from "
            f"{cadence_start.isoformat()}.\n\n"
            + "\n".join(lines)
            + "\n\nThis is a one-time baseline message.\n")
        out.append(Touch(key_id, "baseline", False,
                         f"[BASELINE] {dept}: confirm completed tasks on the dashboard "
                         f"({len(open_rows)} open items)",
                         body, dept, {}))
    return out


# --------------------------------------------------------------------------- #
# Sent-log (idempotency)
# --------------------------------------------------------------------------- #
SENTLOG_HEADER = ["send_date", "task_id", "touch_type", "sent_at_ist"]


def load_sentlog(path: Path) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    with open(path, newline="") as fh:
        return {(r["send_date"], r["task_id"], r["touch_type"]) for r in csv.DictReader(fh)}


def append_sentlog(path: Path, entries: list[tuple[str, str, str]], tz: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    now = datetime.now(ZoneInfo(tz)).isoformat(timespec="seconds")
    with open(path, "a", newline="") as fh:
        w = csv.writer(fh)
        if new:
            w.writerow(SENTLOG_HEADER)
        for send_date, tid, ttype in entries:
            w.writerow([send_date, tid, ttype, now])


# --------------------------------------------------------------------------- #
# Recipients & message building
# --------------------------------------------------------------------------- #
def recipients_for(cfg: dict, dept: str, critical: bool) -> tuple[str, list[str]]:
    to = cfg["department_emails"].get(dept, dept)
    cc: list[str] = []
    qa_cc = cfg.get("qa_oversight_cc", "")
    if qa_cc and qa_cc != to:
        cc.append(qa_cc)
    if critical:
        for a in cfg.get("admin_cc", []):
            if not _is_placeholder(a) and a not in cc and a != to:
                cc.append(a)
    return to, cc


def build_messages(cfg: dict, touches: list[Touch], today: date) -> list[dict]:
    """[{to, cc, subject, body, critical, keys[], department}] — per-task by default,
    or one digest per department when batch_by_department is enabled. Baseline
    touches are always their own email (they are already one-per-department)."""
    baseline = [t for t in touches if t.touch_type == "baseline"]
    normal = [t for t in touches if t.touch_type != "baseline"]
    msgs = []
    for t in baseline:
        to, cc = recipients_for(cfg, t.department, critical=False)
        msgs.append({"to": to, "cc": cc, "subject": t.subject, "body": t.body,
                     "critical": False, "department": t.department,
                     "keys": [(today.isoformat(), t.task_id, t.touch_type)]})
    if not cfg.get("batch_by_department", False):
        for t in normal:
            to, cc = recipients_for(cfg, t.department, t.critical)
            msgs.append({"to": to, "cc": cc, "subject": t.subject, "body": t.body,
                         "critical": t.critical, "department": t.department,
                         "keys": [(today.isoformat(), t.task_id, t.touch_type)]})
        return msgs
    by_dept: dict[str, list[Touch]] = {}
    for t in normal:
        by_dept.setdefault(t.department, []).append(t)
    for dept, ts in sorted(by_dept.items()):
        crit = [t for t in ts if t.critical]
        to, cc = recipients_for(cfg, dept, critical=bool(crit))
        subj = (f"{'[CRITICAL] ' if crit else ''}[{dept}] Daily task reminders — "
                f"{len(ts)} item(s) ({len(crit)} critical) — {today.isoformat()}")
        lines = [f"Daily reminder digest for {dept} — {today.isoformat()} (IST).",
                 f"{len(ts)} item(s), of which {len(crit)} are CRITICAL/overdue.\n"]
        for i, t in enumerate(sorted(ts, key=lambda x: (not x.critical, x.task_id)), 1):
            lines.append(f"{i}. {t.subject}\n   {t.body}")
        msgs.append({"to": to, "cc": cc, "subject": subj, "body": "\n".join(lines),
                     "critical": bool(crit), "department": dept,
                     "keys": [(today.isoformat(), t.task_id, t.touch_type) for t in ts]})
    return msgs


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #
def send_smtp(cfg: dict, msg: dict) -> None:
    user = os.environ.get("MAIL_USERNAME")
    pw = os.environ.get("MAIL_APP_PASSWORD")
    if not user or not pw:
        raise SystemExit("FATAL: MAIL_USERNAME / MAIL_APP_PASSWORD not set for live send.")
    frm = cfg.get("director_email", user)
    mime = MIMEText(msg["body"], "plain", "utf-8")
    mime["Subject"] = msg["subject"]
    mime["From"] = formataddr(("Enicar Reminder System", frm))
    mime["To"] = msg["to"]
    if msg["cc"]:
        mime["Cc"] = ", ".join(msg["cc"])
    if msg.get("critical"):
        mime["X-Priority"] = "1"
        mime["Importance"] = "high"
    ctx = ssl.create_default_context()
    with smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"]) as s:
        s.starttls(context=ctx)
        s.login(user, pw)
        s.sendmail(frm, [msg["to"]] + msg["cc"], mime.as_string())


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #
def run(as_of: date | None = None, dry_run: bool | None = None,
        config_path: Path = DEFAULT_CONFIG, sentlog_path: Path | None = None,
        quiet: bool = False, rows_override: list[dict] | None = None) -> dict:
    cfg = load_config(config_path)
    tz = cfg.get("timezone", "Asia/Kolkata")
    nag_n = int(cfg.get("nag_interval_days", 3))
    if dry_run is None:
        dry_run = os.environ.get("DRY_RUN", str(cfg.get("dry_run_default", True))).lower() != "false"
    today = as_of or today_ist(tz)
    if sentlog_path is None:
        sentlog_path = ROOT / "sent-log" / "sent_log.csv"
    cadence_start = parse_iso(str(cfg.get("cadence_start_date", ""))) or date(2026, 7, 20)

    rows = rows_override if rows_override is not None else load_rows(cfg, dry_run)
    seen = load_sentlog(sentlog_path)

    touches: list[Touch] = []
    if cfg.get("baseline_sweep_enabled", True):
        touches.extend(baseline_touches(rows, seen, cadence_start))
    if today >= cadence_start:
        for row in rows:
            touches.extend(compute_touches_for_row(row, today, nag_n))

    fresh = [t for t in touches
             if (today.isoformat(), t.task_id, t.touch_type) not in seen]
    messages = build_messages(cfg, fresh, today)

    logdir = ROOT / "data" / "dry-run-logs"
    logdir.mkdir(parents=True, exist_ok=True)
    blocks, sent_keys = [], []
    for m in messages:
        blocks.append(
            f"--- {'DRY-RUN' if dry_run else 'SENT'} "
            f"{'[CRITICAL] ' if m['critical'] else ''}[{m['department']}] {today.isoformat()}\n"
            f"TO: {m['to']}\nCC: {', '.join(m['cc']) if m['cc'] else '(none)'}\n"
            f"PRIORITY: {'high (X-Priority: 1)' if m['critical'] else 'normal'}\n"
            f"SUBJECT: {m['subject']}\n{m['body']}\n")
        if not dry_run:
            send_smtp(cfg, m)
        sent_keys.extend(m["keys"])

    if dry_run:
        (logdir / f"{today.isoformat()}.log").write_text(
            f"# DRY-RUN reminder log {today.isoformat()} (IST) — "
            f"{len(messages)} message(s), {len(fresh)} touch(es)\n\n" + "\n".join(blocks))
    if sent_keys:
        append_sentlog(sentlog_path, sent_keys, tz)

    crit_n = sum(1 for t in fresh if t.critical)
    summary = {"date": today.isoformat(), "dry_run": dry_run,
               "touches": len(touches), "fresh": len(fresh), "critical": crit_n,
               "messages": len(messages),
               "by_department": _count(fresh, lambda t: t.department),
               "by_touch": _count(fresh, lambda t: t.touch_type)}
    if not quiet:
        print(f"[{'DRY-RUN' if dry_run else 'LIVE'}] {today.isoformat()}: "
              f"{len(messages)} message(s), {len(fresh)} touch(es) "
              f"({crit_n} critical, {len(touches)-len(fresh)} already sent). "
              f"By dept: {summary['by_department']}")
    return summary


def _count(touches, keyfn) -> dict:
    d: dict[str, int] = {}
    for t in touches:
        d[keyfn(t)] = d.get(keyfn(t), 0) + 1
    return dict(sorted(d.items()))


def main():
    ap = argparse.ArgumentParser(description="Enicar reminder engine v3")
    ap.add_argument("--as-of", help="Run as of this date (YYYY-MM-DD), IST. Default: today.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--sent-log", help="Override sent-log path.")
    args = ap.parse_args()
    as_of = parse_iso(args.as_of) if args.as_of else None
    if args.as_of and as_of is None:
        raise SystemExit(f"Bad --as-of date: {args.as_of}")
    run(as_of=as_of, config_path=Path(args.config),
        sentlog_path=Path(args.sent_log) if args.sent_log else None)


if __name__ == "__main__":
    main()
