# Data Model: Fix Top Movers Auto-Sync Reliability

No new entities and no schema changes. This fix is a scheduling-reliability and observability
change; the existing model is sufficient.

## Existing Entities (reference only — unchanged)

### AutoScannerSettings

Source: [backend/apps/trading/models.py:31-41](../../backend/apps/trading/models.py#L31-L41)

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOne → User | One settings row per operator |
| `enabled` | bool, default `False` | Whether auto-register/auto-sync is turned on |
| `top_n` | PositiveSmallInt, default `5` | Gainers/losers count per run |
| `quote_asset` | str, default `"USDT"` | Quote asset filter |
| `last_synced_at` | datetime, nullable | Timestamp of the most recent **successful** sync — this fix's fix is verified against this field advancing on the automatic cadence |
| `created_at` / `updated_at` | datetime | Standard bookkeeping |

No new fields are added here. `last_synced_at` already carries the semantics FR-002 requires
("reflect the most recent successful sync, whether automatic or manual") — the periodic task
already writes it via `sync_top_movers_to_scanner` on success; the fix is to make that success
path actually execute on schedule, and to record failures visibly (see below) rather than
introducing a new field for sync health.

### BotLog (reused, not new)

Source: referenced via `_log()` in
[backend/apps/trading/services/auto_scanner_service.py:7-12](../../backend/apps/trading/services/auto_scanner_service.py#L7-L12)

Existing per-user log entries, already queryable via `GET /api/logs` and broadcast over the
WebSocket. This fix adds a **failure**-path call into this same existing mechanism from
`auto_register_top_movers` (currently only success paths — `added`/`removed` — call `_log()`; the
task-level `except` branch only calls the server-side `logger.exception`). No new model, field, or
log level is introduced — `BotLog.Level.ERROR` (or the existing level enum's closest equivalent)
is used exactly as other error paths in this codebase already do.

## State Transitions

None. `AutoScannerSettings.enabled` is a simple boolean toggle already implemented; this fix does
not add new states.
