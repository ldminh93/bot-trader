# Implementation Plan: Fix Top Movers Auto-Sync Reliability

**Branch**: `002-fix-top-movers-sync` (no git repository is in use for this checkout; this is the
feature directory slug used as the working label) | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-fix-top-movers-sync/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command. See `.specify/templates/plan-template.md` for the execution workflow.

## Summary

The operator confirmed the manual "Sync now" action always works, but the recurring 15-minute
automatic sync (`auto_register_top_movers`, a Celery Beat task) never actually fires — the "Last
synced" timestamp goes stale indefinitely while auto-register stays enabled. A code review of the
scheduling wiring (`CELERY_BEAT_SCHEDULE`, `app.autodiscover_tasks()`, the task itself, the
underlying `sync_top_movers_to_scanner` service function) found no logic bug: the task name,
schedule entry, and app autodiscovery path line up correctly, and the manual endpoint calls the
exact same service function. That rules out the sync logic itself and points at the scheduling
*infrastructure* — most likely the `celery_beat` and/or `celery_worker` process not staying up
(docker-compose defines no `restart` policy for either, and the "Local development" flow requires
three separate long-running terminals with nothing to notice if one dies), combined with the
periodic task's per-user exception handling only writing to the server-side Python logger — never
to the operator-visible `BotLog`/`GET /api/logs` channel — so a recurring failure would be invisible
to the operator even if it were the cause. The plan is to (1) make the two Celery processes
self-heal via Compose restart policies, (2) route periodic-sync failures through the existing
`BotLog` mechanism so they are visible through the log surface that already exists today (not a new
UI element — the same plumbing `_log()` already uses for successful syncs), and (3) add regression
coverage for the `auto_register_top_movers` task itself, which currently has no test even though the
underlying service function does.

## Technical Context

**Language/Version**: Python 3.11 (Django 5 backend), no frontend change required for this fix

**Primary Dependencies**: Django 5, Django REST Framework, Celery (worker + beat), Redis (broker),
existing `apps.trading` service layer (`auto_scanner_service.py`, `tasks.py`)

**Storage**: PostgreSQL (Docker) / SQLite (local dev) — no schema change required;
`AutoScannerSettings.last_synced_at` already exists

**Testing**: `pytest` (`backend/apps/trading/tests/`)

**Target Platform**: Linux containers via Docker Compose (`celery_worker`, `celery_beat`,
`backend` services) and the equivalent local-dev processes described in README

**Project Type**: Web application (Next.js frontend + Django backend) — this fix is backend/
infrastructure-only; no frontend code changes

**Performance Goals**: N/A — this is a reliability fix for an existing 15-minute recurring job, not
a throughput or latency change

**Constraints**: Fix MUST NOT change which symbols get added/removed/skipped (FR-006) and MUST NOT
alter the manual "Sync now" behavior (FR-005)

**Scale/Scope**: Single recurring Celery Beat entry (`auto-register-top-movers`) affecting all users
with `AutoScannerSettings.enabled=True`; no new entities, no new API endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **I. Paper-First Safety Gate** — N/A. This fix does not touch order placement, the live-trading
  flag, or credential handling. PASS.
- **II. Test-First for Trading Logic** — The changed code (`auto_register_top_movers`) is not
  itself indicator/scoring/risk logic, so this principle's mandatory pytest coverage does not
  strictly apply, but the constitution's Development Workflow section still expects test coverage
  for backend changes. This plan adds a test for the periodic task per Phase 1/tasks. PASS.
- **III. Risk & Position Discipline** — N/A. No change to entry gates, scoring, or position sizing.
  FR-006 explicitly preserves existing add/remove/skip rules. PASS.
- **IV. Secure Credential Handling** — N/A. No credential or secret handling touched. PASS.
- **V. Graceful Degradation & Observability** — Directly relevant: today a failed periodic sync is
  only written to the server-side Python logger, not to the operator-visible `BotLog`/`GET
  /api/logs` channel, so a real recurring failure would be undetectable by the operator — in
  tension with "errors that affect trading decisions MUST surface... rather than being swallowed."
  Resolved in this plan by routing periodic-sync failures through the existing `_log()`/`BotLog`
  path already used for successful syncs — this reuses existing plumbing, it does not add a new UI
  element, so it does not conflict with the spec's FR-007 (no new warning UI). PASS with this
  addition included in scope.
- **VI. Simplicity Across the Stack** — The fix is a Compose restart-policy change, reuse of an
  existing logging path, and a test — no new service, queue, or framework introduced. PASS.

No violations requiring justification in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/002-fix-top-movers-sync/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/            # Phase 1 output (/speckit-plan command) — no API contract changes
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
docker-compose.yml                                   # add restart policy to celery_worker/celery_beat

backend/
├── config/
│   └── settings.py                                   # CELERY_BEAT_SCHEDULE (reference only — no change expected)
└── apps/trading/
    ├── tasks.py                                       # auto_register_top_movers — route failures to BotLog
    ├── services/
    │   └── auto_scanner_service.py                    # sync_top_movers_to_scanner (reference only — unchanged)
    └── tests/
        └── test_auto_scanner_service.py               # add coverage for the periodic task wrapper itself

frontend/                                              # no changes — manual "Sync now" UI is unaffected
```

**Structure Decision**: This is a backend-only reliability fix within the existing Web application
structure (`backend/` Django + Celery, `frontend/` Next.js). No new services, directories, or API
endpoints are introduced; the change lives in `backend/apps/trading/tasks.py`, its test file, and
`docker-compose.yml`.

## Complexity Tracking

No Constitution Check violations — this section is not applicable.
