/**
 * Enicar Master Reminder — write-back web app (Google Apps Script).
 *
 * Deployed as a web app (execute as: Me; access: Anyone). The dashboard posts
 * form-encoded requests here. Three actions per task:
 *   action=tick_action     task_id
 *   action=tick_report     task_id [report_link]
 *   action=reschedule      task_id new_due_date(YYYY-MM-DD) reason
 * Plus: action=health (GET) for a reachability check.
 *
 * Every mutation appends an immutable row to the AuditLog tab:
 *   timestamp_ist | task_id | department | action | field | old_value | new_value | reason | source
 * Audit rows are append-only — nothing in this script ever edits or deletes them.
 *
 * GMP notes:
 *  - The MASTER tab is the register the dashboard and email engine read.
 *  - rescheduled_from always preserves the ORIGINAL due date (first reschedule
 *    sets it; later reschedules do not overwrite it).
 *  - report_due_date is recomputed on reschedule: +10 days from the new due date
 *    (month-window tasks: 10 days after the end of the new month).
 *  - A task rescheduled 2+ times gets an extra 'reschedule_flag' audit row so the
 *    repeated-push signal is itself part of the record.
 */

var MASTER_TAB = 'MASTER';
var AUDIT_TAB = 'AuditLog';
var TZ = 'Asia/Kolkata';

function doGet(e) {
  var p = (e && e.parameter) || {};
  if (p.action === 'health') {
    return json_({ ok: true, service: 'enicar-reminder-writeback', time_ist: nowIst_() });
  }
  return json_({ ok: false, error: 'POST tick_action / tick_report / reschedule; GET action=health' });
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(20000); // serialize concurrent ticks
  try {
    var p = (e && e.parameter) || {};
    var action = String(p.action || '');
    var taskId = String(p.task_id || '').trim();
    if (!taskId) return json_({ ok: false, error: 'task_id required' });

    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(MASTER_TAB);
    if (!sheet) return json_({ ok: false, error: 'MASTER tab not found' });
    var data = sheet.getDataRange().getValues();
    var head = data[0].map(String);
    var col = {};
    head.forEach(function (h, i) { col[h.trim()] = i; });
    var required = ['task_id', 'department', 'due_type', 'due_date', 'report_due_date',
      'action_done_date', 'action_status', 'report_done_date', 'report_status',
      'report_link', 'rescheduled_from', 'reschedule_reason'];
    for (var i = 0; i < required.length; i++) {
      if (!(required[i] in col)) return json_({ ok: false, error: 'missing column ' + required[i] });
    }

    var rowIdx = -1;
    for (var r = 1; r < data.length; r++) {
      if (String(data[r][col.task_id]).trim() === taskId) { rowIdx = r; break; }
    }
    if (rowIdx < 0) return json_({ ok: false, error: 'task_id not found: ' + taskId });

    var row = data[rowIdx];
    var dept = String(row[col.department]);
    var today = todayIst_();

    function setCell(field, value) {
      sheet.getRange(rowIdx + 1, col[field] + 1).setValue(value);
    }

    if (action === 'tick_action') {
      if (String(row[col.action_status]).toLowerCase() === 'done') {
        return json_({ ok: true, noop: true, message: 'action already done' });
      }
      setCell('action_done_date', today);
      setCell('action_status', 'done');
      audit_(ss, taskId, dept, 'tick_action', 'action_status',
             String(row[col.action_status]), 'done', '', 'dashboard');
      return json_({ ok: true, task_id: taskId, action_done_date: today });
    }

    if (action === 'tick_report') {
      if (String(row[col.report_status]).toLowerCase() === 'done') {
        return json_({ ok: true, noop: true, message: 'report already done' });
      }
      var link = String(p.report_link || '').trim();
      setCell('report_done_date', today);
      setCell('report_status', 'done');
      if (link) setCell('report_link', link);
      audit_(ss, taskId, dept, 'tick_report', 'report_status',
             String(row[col.report_status]), 'done' + (link ? ' (' + link + ')' : ''), '', 'dashboard');
      return json_({ ok: true, task_id: taskId, report_done_date: today });
    }

    if (action === 'reschedule') {
      var newDue = String(p.new_due_date || '').trim();
      var reason = String(p.reason || '').trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(newDue)) {
        return json_({ ok: false, error: 'new_due_date must be YYYY-MM-DD' });
      }
      if (!reason) return json_({ ok: false, error: 'a reason is required to reschedule' });
      var oldDue = isoDate_(row[col.due_date]);
      // preserve the ORIGINAL date across multiple reschedules
      var origFrom = isoDate_(row[col.rescheduled_from]);
      if (!origFrom) setCell('rescheduled_from', oldDue);
      setCell('due_date', newDue);
      setCell('reschedule_reason', reason);
      setCell('report_due_date', reportDue_(newDue, String(row[col.due_type])));
      audit_(ss, taskId, dept, 'reschedule', 'due_date', oldDue, newDue, reason, 'dashboard');
      // repeated-push signal: count reschedules incl. this one; flag at 2+
      var count = rescheduleCount_(ss, taskId);
      if (count >= 2) {
        audit_(ss, taskId, dept, 'reschedule_flag', 'reschedule_count',
               String(count - 1), String(count),
               'task rescheduled ' + count + ' times — director attention', 'system');
      }
      return json_({ ok: true, task_id: taskId, due_date: newDue, reschedule_count: count });
    }

    return json_({ ok: false, error: 'unknown action: ' + action });
  } finally {
    lock.releaseLock();
  }
}

/* ------------------------- helpers ------------------------- */

function audit_(ss, taskId, dept, action, field, oldVal, newVal, reason, source) {
  var sheet = ss.getSheetByName(AUDIT_TAB);
  if (!sheet) {
    sheet = ss.insertSheet(AUDIT_TAB);
    sheet.appendRow(['timestamp_ist', 'task_id', 'department', 'action', 'field',
                     'old_value', 'new_value', 'reason', 'source']);
  }
  sheet.appendRow([nowIst_(), taskId, dept, action, field, oldVal, newVal, reason, source]);
}

function rescheduleCount_(ss, taskId) {
  var sheet = ss.getSheetByName(AUDIT_TAB);
  if (!sheet) return 0;
  var data = sheet.getDataRange().getValues();
  var n = 0;
  for (var r = 1; r < data.length; r++) {
    if (String(data[r][1]).trim() === taskId && String(data[r][3]) === 'reschedule') n++;
  }
  return n;
}

function reportDue_(dueIso, dueType) {
  var parts = dueIso.split('-').map(Number);
  var d;
  if (dueType === 'month_window') {
    d = new Date(parts[0], parts[1], 0);           // last day of the due month
  } else {
    d = new Date(parts[0], parts[1] - 1, parts[2]);
  }
  d.setDate(d.getDate() + 10);
  return Utilities.formatDate(d, TZ, 'yyyy-MM-dd');
}

function isoDate_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, TZ, 'yyyy-MM-dd');
  var s = String(v || '').trim();
  return s ? s.substring(0, 10) : '';
}

function nowIst_() {
  return Utilities.formatDate(new Date(), TZ, "yyyy-MM-dd'T'HH:mm:ss");
}

function todayIst_() {
  return Utilities.formatDate(new Date(), TZ, 'yyyy-MM-dd');
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
