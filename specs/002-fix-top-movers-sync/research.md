# Phase 0 Research: Fix Top Movers Auto-Sync Reliability

## Task: Determine why the automatic sync never fires while the manual sync always succeeds

**Decision**: Treat this as an infrastructure/process-supervision reliability gap rather than a
logic bug in `sync_top_movers_to_scanner` — no defect was found anywhere in the scheduling wiring
or the sync function itself. The fix is to (a) make the two Celery processes self-heal, and (b)
make a recurring failure visible to the operator through the log surface that already exists,
since nothing today would show it.

**Rationale** (evidence gathered from the current code):

1. **Task naming and autodiscovery line up correctly.** `backend/config/celery.py` creates the
   Celery app with `app.autodiscover_tasks()`, and `apps/trading/apps.py` declares
   `name = "apps.trading"`, so the auto-discovered dotted task path is
   `apps.trading.tasks.auto_register_top_movers` — exactly the string used in
   `CELERY_BEAT_SCHEDULE["auto-register-top-movers"]["task"]`
   ([settings.py:114-117](../../backend/config/settings.py#L114-L117)). No naming mismatch.
2. **The schedule entry itself is correct.** `schedule: 900.0` seconds = 15 minutes, matching the
   UI copy ("auto-synced every 15 min").
3. **The manual and automatic paths call the identical service function.** `AutoScannerSyncView.post`
   ([views.py:442-445](../../backend/apps/trading/views.py#L442-L445)) and
   `auto_register_top_movers` ([tasks.py:661-667](../../backend/apps/trading/tasks.py#L661-L667))
   both ultimately call `sync_top_movers_to_scanner(...)`. Since the operator confirmed manual sync
   always succeeds, the sync logic itself (Binance lookup, add/remove/skip rules, `last_synced_at`
   write) is demonstrably not the broken part — it works when invoked.
4. **The periodic task swallows exceptions per-user, and only to the server-side logger.**
   `auto_register_top_movers` wraps each user's sync in `try/except Exception: logger.exception(...)`
   ([tasks.py:661-667](../../backend/apps/trading/tasks.py#L661-L667)). This is correct for FR-003/
   FR-004 (one user's failure must not block others or stop future runs) but means a real recurring
   failure would leave no trace the operator can see — `_log()` inside
   `auto_scanner_service.py` writes to `BotLog` (queryable via `GET /api/logs` and broadcast over the
   WebSocket) only on the success paths (`added`, `removed`), never on failure.
5. **Nothing prevents the two Celery processes from silently staying dead.**
   `docker-compose.yml` defines `celery_worker` and `celery_beat` with no `restart` policy and no
   healthcheck (unlike `postgres`/`redis`, which have both). If either process crashes or is never
   started, Compose gives no signal and nothing brings it back. The README's "Local development"
   section separately requires the operator to keep two additional terminals running
   (`celery -A config worker` and `celery -A config beat`) indefinitely, with nothing to notice if
   one of them dies.

Given (1)-(3) rule out a code defect in the sync logic itself, and (5) is a documented, concrete gap
with no compensating control, the leading hypothesis is that the `celery_beat` and/or
`celery_worker` process is not continuously running in the operator's environment. (4) means that
even after fixing the process-supervision gap, a *future* recurrence would again be invisible to the
operator unless failures are routed to `BotLog`.

**Alternatives considered**:

- *Add a database-backed periodic-task scheduler (e.g., `django-celery-beat`)* — rejected: this
  project uses the plain in-code `CELERY_BEAT_SCHEDULE` dict deliberately (Principle VI, Simplicity
  Across the Stack); introducing a new scheduler backend is unjustified complexity for a reliability
  fix that doesn't require dynamic schedule editing.
- *Add a dedicated health-check/monitoring endpoint or new "sync health" UI* — rejected: the spec's
  FR-007 explicitly places a new warning UI out of scope; the operator only asked for the automatic
  sync to work.
- *Rewrite `sync_top_movers_to_scanner` itself* — rejected: no evidence of a defect there (manual
  sync already succeeds every time using the same function).

## Task: Confirm no schema or API contract changes are needed

**Decision**: None needed. `AutoScannerSettings.last_synced_at` already exists
([models.py:31-41](../../backend/apps/trading/models.py#L31-L41)) and `GET/PUT
/api/scanner/auto-settings` and `POST /api/scanner/sync`
([urls.py:36-37](../../backend/apps/trading/urls.py#L36-L37)) already return/accept the fields this
fix needs. This is a backend scheduling-reliability fix; the API surface is unchanged.

**Rationale**: FR-005 and FR-006 require the manual sync and the existing add/remove/skip rules to
be unaffected — confirmed no serializer, model, or URL change is required to satisfy that constraint.

**Alternatives considered**: N/A — no design space here, just a verification step.
