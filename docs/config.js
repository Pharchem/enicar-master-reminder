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
  SHEET_CSV_URL: "https://docs.google.com/spreadsheets/d/e/2PACX-1vT3x9hcQTOl8tKtrzcS7tLas3u268_2lx1rwAhmpgjWHVbryTPSxxzOlljYRfLV5k6hS8KPDzlrmhcv/pub?gid=1690372004&single=true&output=csv",
  AUDIT_CSV_URL: "https://docs.google.com/spreadsheets/d/e/2PACX-1vT3x9hcQTOl8tKtrzcS7tLas3u268_2lx1rwAhmpgjWHVbryTPSxxzOlljYRfLV5k6hS8KPDzlrmhcv/pub?gid=243181721&single=true&output=csv",
  WRITEBACK_URL: "https://script.google.com/macros/s/AKfycbyzshZdG5MTrLNXyLRbQ0KmZZnCVzblMF4xyV6yvQW9Gk-cj1OJkVcov3RZkPoNZ8yhuA/exec",
  SNAPSHOT_CSV: "MASTER_consolidated.csv",
  LOCAL_AUDIT: "/audit.csv",
  LOCAL_WRITEBACK: "/writeback",
};
