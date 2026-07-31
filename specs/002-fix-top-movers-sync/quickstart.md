# Quickstart: Validate Top Movers Auto-Sync Reliability

## Prerequisites

- Docker Compose stack running (`docker compose up --build`), or the local-dev backend + Celery
  worker + Celery beat processes per the README's "Local development" section.
- A logged-in user with `AutoScannerSettings.enabled = True` (toggle "Auto-register top movers to
  scanner" on in the Top Movers screen).

## Scenario 1 — Automatic sync advances without clicking "Sync now" (FR-001, SC-001)

1. Enable auto-register and note the current "Last synced" time (or clear it via the API/admin so
   the check is unambiguous).
2. Do **not** click "Sync now".
3. Wait for one scheduling interval. To avoid waiting the full 15 minutes during manual
   validation, trigger the same Celery task directly instead of waiting:
   ```bash
   cd backend
   ../.venv/bin/celery -A config call apps.trading.tasks.auto_register_top_movers
   ```
4. Reload the Top Movers screen (or `GET /api/scanner/auto-settings`).
5. **Expected**: `last_synced_at` has advanced to a new timestamp, with no manual sync click
   involved.

## Scenario 2 — Restart resilience (research.md hypothesis)

1. With `docker compose up` running, stop the `celery_beat` container:
   `docker compose stop celery_beat`.
2. Confirm it comes back on its own per the new restart policy:
   `docker compose ps celery_beat` should show it running again shortly, without a manual
   `docker compose up` / `start`.
3. Repeat for `celery_worker`.
4. **Expected**: both processes automatically return to a running state after being stopped,
   rather than staying down indefinitely.

## Scenario 3 — Manual "Sync now" is unaffected (FR-005, SC-003)

1. Click "Sync now" on the Top Movers screen.
2. **Expected**: identical behavior to before this fix — immediate success, `last_synced_at`
   updates immediately, and the on-screen "Added / Removed / Kept" summary appears as it does
   today.

## Scenario 4 — A failed automatic sync is visible to the operator (Constitution Principle V)

1. Temporarily force `sync_top_movers_to_scanner` to raise for one test user (e.g., via a monkeypatch
   in a test, not in a live environment) and invoke `auto_register_top_movers()`.
2. **Expected**: a `BotLog` entry (level `ERROR`) is created for that user and is visible via
   `GET /api/logs`; other users' scheduled syncs are unaffected (FR-004); the task itself does not
   raise (FR-003 — future scheduled runs still occur).

## Automated checks

```bash
cd backend
pytest apps/trading/tests/test_auto_scanner_service.py -k auto_register_top_movers
```

Expected: new/updated tests covering the periodic task wrapper (not just the underlying service
function) pass — see `tasks.md` for the exact test cases to add.
