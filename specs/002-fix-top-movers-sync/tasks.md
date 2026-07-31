---

description: "Task list for feature implementation"
---

# Tasks: Fix Top Movers Auto-Sync Reliability

**Input**: Design documents from `specs/002-fix-top-movers-sync/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [quickstart.md](./quickstart.md)

**Tests**: Included. Not explicitly requested in spec.md, but required by the project constitution's
Development Workflow ("Every PR touching `backend/` trading-adjacent logic MUST include or update
`pytest` coverage") and by `research.md`'s decision to close the existing test gap around the
`auto_register_top_movers` task.

**Organization**: This feature has a single user story (P1). All implementation tasks live under
that story's phase; there is no Foundational phase because nothing else depends on a shared
prerequisite beyond what the story itself needs.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1)
- Include exact file paths in descriptions

## Path Conventions

Web app structure per plan.md: `backend/` (Django + Celery) and `frontend/` (Next.js, unaffected by
this fix). All paths below are relative to the repository root.

---

## Phase 1: Setup

No setup tasks required — this is a reliability fix on an existing, already-initialized project;
there is no new scaffolding, dependency, or tooling to introduce.

---

## Phase 2: Foundational (Blocking Prerequisites)

Not applicable — this feature has only one user story, so there is no shared prerequisite work that
would otherwise block multiple stories. All prerequisite work is scoped directly into User Story 1
below.

---

## Phase 3: User Story 1 - Automatic sync actually runs on its own (Priority: P1) 🎯 MVP

**Goal**: The 15-minute automatic top-movers sync actually runs on its own (self-heals if its Celery
processes die, and a per-user failure is visible to the operator), without changing the manual
"Sync now" behavior or the existing add/remove/skip rules.

**Independent Test**: With auto-register enabled and without clicking "Sync now", trigger
`apps.trading.tasks.auto_register_top_movers` directly (or wait 15+ minutes) and confirm
`last_synced_at` advances; separately, stop the `celery_beat`/`celery_worker` containers and confirm
they come back on their own.

### Tests for User Story 1 ⚠️

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation (T004-T005 below)**

- [X] T001 [US1] Add test asserting `auto_register_top_movers()` calls `sync_top_movers_to_scanner`
  once for every `AutoScannerSettings` row with `enabled=True`, and does not call it for rows with
  `enabled=False`, in `backend/apps/trading/tests/test_auto_scanner_service.py`
- [X] T002 [US1] Add test asserting that when `sync_top_movers_to_scanner` raises for one user's
  settings, `auto_register_top_movers()` still calls it for every remaining enabled user (per-user
  failure isolation, per FR-003/FR-004), in `backend/apps/trading/tests/test_auto_scanner_service.py`
- [X] T003 [US1] Add test asserting that when `sync_top_movers_to_scanner` raises for a user,
  `auto_register_top_movers()` results in a `BotLog` row for that user with `level=BotLog.Level.ERROR`
  and a message that includes the symbol placeholder `"SCANNER"` and the failure reason, in
  `backend/apps/trading/tests/test_auto_scanner_service.py`

### Implementation for User Story 1

- [X] T004 [US1] In `backend/apps/trading/services/auto_scanner_service.py`, rename the module-private
  `_log(user, symbol, message)` helper to a public `log_scanner_event(user, symbol, message,
  level=BotLog.Level.INFO)`, threading the new `level` parameter into the `BotLog.objects.create(...)`
  call and the `send_discord_alert(...)` call; update the existing internal call sites in the same
  file to use the new name (default level keeps their behavior unchanged) (depends on T001-T003
  existing as failing tests)
- [X] T005 [US1] In `backend/apps/trading/tasks.py`, update the `except Exception` branch inside
  `auto_register_top_movers()` to call
  `log_scanner_event(settings_obj.user, "SCANNER", f"Automatic top-movers sync failed: {exc}",
  level=BotLog.Level.ERROR)` in addition to the existing `logger.exception(...)` call, so the failure
  is visible via `GET /api/logs` and the WebSocket log channel, not just the server-side logger
  (depends on T004). **Implementation note (found while running T007's tests against a real, Redis-less
  environment)**: the `log_scanner_event` call itself is wrapped in its own nested `try/except` —
  without it, a broadcast/Discord failure while *recording* the error would propagate out of the
  `except` block and abort the loop for every remaining user, which would be a worse regression than
  the original bug.
- [X] T006 [P] [US1] Add `restart: unless-stopped` to the `celery_worker` and `celery_beat` service
  definitions in `docker-compose.yml` so both processes self-heal after a crash or being stopped
  (independent of T004/T005 — different concern, different file)
- [X] T007 [US1] Run `cd backend && pytest apps/trading/tests/test_auto_scanner_service.py` and
  confirm T001-T003 now pass against the T004-T005 implementation (depends on T001-T006). Result:
  6/6 passed. Full suite (`pytest`) also run: 85 passed, 7 pre-existing failures in
  `test_risk.py`/`test_paper_trading.py` (a `calculate_risk_plan() got multiple values for argument
  'ma7'` signature mismatch) — unrelated to this change (no file this feature touches is on that
  call path) and left as-is; not fixed here to avoid unrequested scope creep.
- [ ] T008 [US1] Manually validate quickstart.md Scenario 1: with auto-register enabled and without
  clicking "Sync now", run
  `cd backend && ../.venv/bin/celery -A config call apps.trading.tasks.auto_register_top_movers` and
  confirm `last_synced_at` (via `GET /api/scanner/auto-settings` or the Top Movers screen) advances
  (depends on T004-T005). **Not run**: no live Celery worker/beat + reachable Redis in this
  environment (Redis connection to localhost:6379 refused during T007) — requires the operator's own
  running stack.
- [ ] T009 [US1] Manually validate quickstart.md Scenario 2: with `docker compose up` running, run
  `docker compose stop celery_beat` then `docker compose ps celery_beat` and confirm it returns to a
  running state on its own; repeat for `celery_worker` (depends on T006). **Not run**: no Docker
  Compose stack running in this environment — requires the operator's own environment.
- [ ] T010 [US1] Manually validate quickstart.md Scenario 3: click "Sync now" on the Top Movers
  screen and confirm identical behavior to before this fix — immediate success, `last_synced_at`
  updates immediately, "Added / Removed / Kept" summary appears as today (regression check; depends
  on T004-T006). **Not run**: no running frontend/backend/browser session available in this
  environment — requires the operator's own environment.

**Checkpoint**: At this point, the automatic sync self-heals its Celery processes, runs on schedule,
surfaces per-user failures via the existing log channel, and the manual sync path and existing
add/remove/skip rules are unchanged and verified.

---

## Phase 4: Polish & Cross-Cutting Concerns

Not applicable — validation is covered by T007-T010 above; there is no additional documentation,
performance, or cross-story cleanup in scope for this single-story fix.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: None — no tasks.
- **Foundational (Phase 2)**: None — no tasks.
- **User Story 1 (Phase 3)**: Can start immediately.
  - Tests (T001-T003) MUST be written and confirmed failing before T004-T005.
  - T004 before T005 (T005 calls the function T004 introduces).
  - T006 has no dependency on T004/T005 and can proceed in parallel with them.
  - T007 depends on T001-T006 (validates the implementation against the tests).
  - T008-T010 depend on the implementation tasks they each validate (see per-task notes above).

### Within User Story 1

- Tests before implementation (T001-T003 before T004-T005).
- `log_scanner_event` introduced before it is called from the task (T004 before T005).
- Docker Compose restart policy (T006) is independent of the BotLog logging change and can be done
  in parallel.
- Automated test run (T007) before manual validation (T008-T010), so regressions are caught early.

### Parallel Opportunities

- T006 (docker-compose.yml) can be done in parallel with T004-T005 (Python source changes) — different
  files, no shared dependency.
- T001-T003 are sequential in practice because they land in the same test file, even though they have
  no logical dependency on each other.

---

## Parallel Example: User Story 1

```bash
# T006 can run alongside T004 since they touch different files with no shared dependency:
Task: "Add restart: unless-stopped to celery_worker and celery_beat in docker-compose.yml"
Task: "Rename _log to log_scanner_event with a level parameter in backend/apps/trading/services/auto_scanner_service.py"
```

---

## Implementation Strategy

### MVP = the entire feature

This feature has one user story, so there is no incremental "MVP subset" — completing User Story 1
(T001-T010) delivers the entire fix. Recommended order:

1. T001-T003 (tests, confirm they fail against current code).
2. T004-T005 (BotLog visibility for periodic-sync failures) and T006 (Compose restart policy) — T006
   can be done in parallel with T004-T005.
3. T007 (automated tests pass).
4. T008-T010 (manual quickstart validation, including the regression check on manual "Sync now").
