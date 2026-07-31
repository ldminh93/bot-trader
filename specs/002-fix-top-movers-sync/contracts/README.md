# Contracts: Fix Top Movers Auto-Sync Reliability

No API contract changes. This is a scheduling-reliability fix internal to the backend
(`docker-compose.yml` restart policy + the `auto_register_top_movers` Celery task's failure
handling). The existing endpoints below are unaffected and documented here only for reference —
their request/response shape does not change:

- `GET /api/scanner/auto-settings` — returns `AutoScannerSettings` (unchanged)
- `PUT /api/scanner/auto-settings` — updates `AutoScannerSettings` (unchanged)
- `POST /api/scanner/sync` — triggers a manual sync (unchanged; this is the path that already
  works today and must keep working identically per FR-005)
- `GET /api/logs` — will start including sync-failure entries for the operator's own account once
  this fix routes failures through the existing `BotLog` mechanism (additive data, not a shape
  change — same `BotLogSerializer` fields as every other log entry)
