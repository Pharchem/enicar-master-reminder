// Dashboard configuration (v3).
//
// PRODUCTION: set all three URLs after completing SETUP.md:
//   SHEET_CSV_URL  — published CSV of the MASTER tab
//   AUDIT_CSV_URL  — published CSV of the AuditLog tab (drives the reschedule watch list)
//   WRITEBACK_URL  — deployed Apps Script web-app URL (ticks + reschedules post here)
//
// LOCAL TEST: run `python3 engine/mock_writeback.py --port 8747` and open
// http://localhost:8747/index.html — with the placeholders below unchanged, the
// dashboard auto-uses the local snapshot, /audit.csv and /writeback mock endpoint.
window.ENICAR_CONFIG = {
  SHEET_CSV_URL: "PASTE_PUBLISHED_MASTER_CSV_URL_HERE",
  AUDIT_CSV_URL: "PASTE_PUBLISHED_AUDITLOG_CSV_URL_HERE",
  WRITEBACK_URL: "PASTE_DEPLOYED_APPS_SCRIPT_WEBAPP_URL_HERE",
  SNAPSHOT_CSV: "MASTER_consolidated.csv",
  LOCAL_AUDIT: "/audit.csv",
  LOCAL_WRITEBACK: "/writeback",
};
