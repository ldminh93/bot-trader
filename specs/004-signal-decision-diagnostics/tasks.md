# Tasks: Signal Decision Ledger & Trade Diagnostics

**Input**: Design documents in `/specs/004-signal-decision-diagnostics/` (plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md)

**Tests**: INCLUDED. Constitution Principle II (test-first for trading-adjacent logic) applies: write each test, confirm it fails, then implement. Existing suites (`test_signal.py`, `test_risk.py`, `test_paper_trading.py`, `test_live_trading_service.py`) must stay green throughout (SC-006).

**Implementation notes** (deviations from the plan, all behavior-neutral):
- `GateCode` lives in `services/gate_codes.py` (dependency-free so `signal_service` can use it) and is re-exported by `decision_ledger_service`.
- T021: instead of editing every close path, a `post_save` hook on `Trade` (`signals.py`) finalizes R/MFE/MAE for any save of a CLOSED trade — covers paper, live, manual, follower-sync and auto-heal closes without touching those services. Per-cycle `update_excursion` is called from `process_config`.
- Extra gate codes were added for the confirmation filters in `market_snapshot_service` (which turn a scored signal into NO_TRADE).
- Exit quality reports `winners_avg_mae_r` / `losers_avg_mfe_r` instead of a `stops_too_tight_pct` (a percentage would need post-close price data that is not stored).
- Diagnostics takes an optional `window` (1h/4h/24h, default 4h) selecting which forward-outcome window gate value is judged on.
- T031/T035 remain open: they need a running stack and a browser session.

**Format**: `- [ ] [ID] [P?] [Story] Description with file path` — `[P]` = different files, no dependency on an incomplete task.

**Paths**: Backend `backend/apps/trading/`, frontend `frontend/`. Run tests from `backend/` with `pytest`.

## Phase 1: Setup

- [X] T001 Inventory every entry-rejection site in `process_config` (`backend/apps/trading/tasks.py`) and every `NO_TRADE` return in `score_signal` (`backend/apps/trading/services/signal_service.py`); write the final list into the "GateCode" section of `specs/004-signal-decision-diagnostics/data-model.md` (code, source location, one-line meaning)

---

## Phase 2: Foundational (blocks all user stories)

- [X] T002 [P] Add `SignalDecision` model per data-model.md (unique `(config, side, result, signal_candle_ts)`; indexes `(user,-created_at)`, `(user,result,-created_at)`, `created_at`) to `backend/apps/trading/models.py`
- [X] T003 [P] Add nullable `r_multiple`, `mfe_pct`, `mae_pct`, `mfe_r`, `mae_r` fields to `Trade` in `backend/apps/trading/models.py`
- [X] T004 Generate migration `backend/apps/trading/migrations/0045_signal_decision_and_trade_excursion.py` (`python manage.py makemigrations trading`) and verify it applies on SQLite and is reversible
- [X] T005 Create `backend/apps/trading/services/decision_ledger_service.py` with the `GateCode` enum (from T001) and stub signatures `record_decision(...)`, `record_rejection(...)`, `record_taken(...)`, `prune_old_decisions(...)`
- [X] T006 [P] Add read-only `r_multiple`, `mfe_r`, `mae_r`, `mfe_pct`, `mae_pct` to the trade serializer in `backend/apps/trading/serializers.py`; extend `backend/apps/trading/tests/test_trades_view.py` to assert they are present and `null` for legacy trades

**Checkpoint**: models, migration and gate enum exist; app boots; existing tests pass.

---

## Phase 3: User Story 1 — Gate value ledger with forward outcomes (P1) 🎯 MVP

**Goal**: Every near-candidate rejection and every taken entry is stored with a stable gate code; 1h/4h/24h forward outcomes are filled from real candles only.

**Independent Test**: Run pytest for the new US1 tests; then follow quickstart steps 2–3 (rows with named gates, no duplicates, outcomes resolve, and stay `pending` when the exchange is unreachable).

### Tests for US1 (write first, confirm they fail)

- [X] T007 [P] [US1] Write `backend/apps/trading/tests/test_decision_ledger.py`: gate-code recorded for representative rejections (funding, TF alignment, max positions, circuit breaker, entry location, `score_signal` hard gates); `TAKEN` row links the trade; duplicate `(config, side, gate, candle_ts)` stored once; low-score non-candidate not recorded; `record_*` raising internally does not raise out; followers (non-staff) produce no rows; `is_paper` copied
- [X] T008 [P] [US1] Write `backend/apps/trading/tests/test_outcome_service.py` with fixture candles: TP1-first → `tp1`, SL-first → `sl`, both in one candle → `ambiguous`, neither → `none`, max favorable/adverse % correct, short-side sign handling, `fetch_klines_range` returning `None` leaves `pending`, 48h pending → `unavailable`, resolved windows never overwritten, default-level derivation (1.5×ATR stop, 1R TP1) when planner levels absent
- [X] T009 [P] [US1] Add tests to `backend/apps/trading/tests/test_binance_service.py` for `fetch_klines_range`: paginates/limits correctly, returns `None` on HTTP error/bad payload, never returns mock candles
- [X] T010 [P] [US1] Add tests to `backend/apps/trading/tests/test_signal.py` asserting `SignalResult.blocked_gate` is set for each hard-gate `NO_TRADE` and `None` on normal results, with all existing assertions unchanged

### Implementation for US1

- [X] T011 [US1] Add optional `blocked_gate: str | None = None` to `SignalResult` and set it (values from `GateCode`) at each internal hard-gate `NO_TRADE` return in `backend/apps/trading/services/signal_service.py` (no change to conditions, scores, or reasons)
- [X] T012 [US1] Implement `record_decision`/`record_rejection`/`record_taken` in `backend/apps/trading/services/decision_ledger_service.py`: near-candidate floor (directional score ≥ 60% of applicable entry threshold, or any post-score gate), signal-candle dedupe via insert-ignore, reference-level capture (planner values when present else ATR defaults with `levels_source`), whole body wrapped in try/except with `logger.exception`, never raises
- [X] T013 [US1] Add `BinanceService.fetch_klines_range(symbol, interval, start_ms, end_ms)` (real data only, returns `None` on any failure, no shared cache, no mock fallback) in `backend/apps/trading/services/binance_service.py`
- [X] T014 [US1] Wire `record_rejection` beside every existing `create_log(...)`+`return` rejection in `process_config` and `record_taken` after trade creation, plus score-level rejection from `signal.blocked_gate` when `signal.signal == "NO_TRADE"`, in `backend/apps/trading/tasks.py` (staff configs only; no logic or ordering changes)
- [X] T015 [US1] Implement `resolve_outcomes(now)` in `backend/apps/trading/services/outcome_service.py`: select decisions with due, unresolved windows; fetch via `fetch_klines_range` (1m candles ≤ 1h, 5m ≤ 24h); compute max favorable/adverse %, first hit, `ambiguous` rule; write each window independently; `pending` on fetch failure; `unavailable` after 48h
- [X] T016 [US1] Add Celery tasks `resolve_decision_outcomes` (every 5 min) and `prune_signal_decisions` (daily, 90-day retention) in `backend/apps/trading/tasks.py` and register both in `CELERY_BEAT_SCHEDULE` in `backend/config/settings.py`
- [X] T017 [US1] Run the US1 tests plus full `pytest`; confirm previously passing tests still pass and record results in the PR description

**Checkpoint**: US1 delivers gate-level evidence via the shell/admin (no UI yet). Register `SignalDecision` in `backend/apps/trading/admin.py` (read-only list with filters by gate/symbol) as part of this checkpoint.

- [X] T018 [P] [US1] Register read-only `SignalDecision` admin (list_display: created_at, symbol, side, result, score, grade; filters: result, symbol, is_paper) in `backend/apps/trading/admin.py`

---

## Phase 4: User Story 2 — R-multiple, MFE, MAE on trades (P1)

**Goal**: Every new trade tracks excursions each cycle and stores final R-multiple on close.

**Independent Test**: `pytest backend/apps/trading/tests/test_excursion.py`, then quickstart step 4 (hand-verify R on a closed paper trade; legacy trades show `null`).

### Tests for US2 (write first)

- [X] T019 [P] [US2] Write `backend/apps/trading/tests/test_excursion.py`: LONG and SHORT MFE/MAE update only on new extremes; values in % and R; R uses `initial_stop_loss`; `r_multiple = realized_pnl / (|entry − initial_stop_loss| × quantity)` with partial exits and fees included in realized PnL; null when `initial_stop_loss` missing/zero; finalize on close for paper and live-closed trades; passive follower trades tracked; legacy trades untouched; failure inside `update_excursion` does not raise

### Implementation for US2

- [X] T020 [US2] Implement `update_excursion(trade, price)` and `finalize_trade_metrics(trade)` in `backend/apps/trading/services/excursion_service.py` (save with `update_fields` only when an extreme changes; exception-safe)
- [X] T021 [US2] Call `update_excursion` each cycle for the open trade in `process_config` after the existing update step, and `finalize_trade_metrics` at every close path (paper close, live update close, early exit, master-close sync to followers, live-sync auto-heal in `backend/apps/trading/services/health_service.py`) in `backend/apps/trading/tasks.py`, `backend/apps/trading/services/paper_trading_service.py`, `backend/apps/trading/services/live_trading_service.py`, `backend/apps/trading/services/position_sync_service.py`, `backend/apps/trading/services/health_service.py` (metric calls only; no PnL/exit logic changes)
- [X] T022 [US2] Run US2 tests plus `test_paper_trading.py`, `test_live_trading_service.py`, `test_early_exit.py`, `test_trades_view.py` and confirm they still pass

**Checkpoint**: US1 and US2 are each independently demonstrable.

---

## Phase 5: User Story 3 — Diagnostics endpoint and page (P2)

**Goal**: One page with gate value, calibration, expectancy (tag, regime × side) and exit quality, filterable, per-user, with low-sample flags.

**Independent Test**: `pytest backend/apps/trading/tests/test_diagnostics_service.py`, then quickstart step 5 (four sections render, n<30 badge, filters, empty state, second user sees nothing of the first).

### Tests for US3 (write first)

- [X] T023 [P] [US3] Write `backend/apps/trading/tests/test_diagnostics_service.py`: gate won/lost/undecided % and net R (`+1R` per would-lose, `−TP1/SL distance` per would-win, 0 for ambiguous/none); score-bucket (10-pt) and grade calibration; expectancy by tag and by regime × side; `low_sample` at n<30; exit quality (give-back, stopped-after-favorable %, stops-too-tight % with MAE ≤ 10% beyond stop); date range and paper/live/all filters; unavailable inputs yield `null` not 0; legacy trades derive R only when `initial_stop_loss` exists; empty data shape
- [X] T024 [P] [US3] Write `backend/apps/trading/tests/test_diagnostics_view.py`: 401 unauthenticated, 400 on bad date/mode, response matches `contracts/api.md`, user A never sees user B's decisions/trades, 10k-decision/1k-trade fixture responds under 3 s

### Implementation for US3

- [X] T025 [US3] Implement `build_diagnostics(user, start, end, mode)` in `backend/apps/trading/services/diagnostics_service.py` (Python aggregation with `only()` field selection, mirroring `analytics_service.py`; shared helper for win rate/avg R/expectancy/low-sample)
- [X] T026 [US3] Add `DiagnosticsView` (query param validation, `IsAuthenticated`, scoped to `request.user`) in `backend/apps/trading/views.py` and route `path("diagnostics", DiagnosticsView.as_view())` in `backend/apps/trading/urls.py`
- [X] T027 [P] [US3] Add Diagnostics response types to `frontend/lib/types.ts` and a `getDiagnostics(start, end, mode)` client in `frontend/lib/api.ts`
- [X] T028 [P] [US3] Create page `frontend/app/diagnostics/page.tsx` following the `frontend/app/analytics/page.tsx` pattern (`PageFrame`/`AppShell`)
- [X] T029 [US3] Create `frontend/components/diagnostics/diagnostics-console.tsx`: date-range and paper/live/all controls; four sections as plain tables matching existing analytics styling; low-sample badge on n<30 rows; empty state; footnotes for excursion granularity (~20s cycle), default reference levels, and "decisions come from the master account"
- [X] T030 [US3] Add a "Diagnostics" nav entry in `frontend/components/app-shell.tsx`
- [ ] T031 [US3] Exercise the page against `npm run dev` per the constitution's frontend verification rule (golden path, filters, empty state, second user isolation) and note results in the PR description

**Checkpoint**: all three stories independently functional.

---

## Phase 6: Polish & Cross-Cutting

- [X] T032 [P] Add a ledger-failure safety test in `backend/apps/trading/tests/test_decision_ledger.py`: patch `record_decision` and `update_excursion` to raise and assert `process_config` completes with identical trade outcomes (FR-008)
- [X] T033 [P] Add a paper-mode regression test in `backend/apps/trading/tests/test_run_active_bots.py`: same inputs produce the same entries/exits with the feature present (SC-006)
- [X] T034 [P] Update `README.md` API section with `GET /api/diagnostics` and the new beat tasks
- [ ] T035 Run the full quickstart (`specs/004-signal-decision-diagnostics/quickstart.md`) end to end and the entire `pytest` suite; confirm Principle I gates untouched (no diffs in order-placement paths beyond metric calls)

---

## Dependencies & Execution Order

- Phase 1 → Phase 2 → (Phase 3 ‖ Phase 4) → Phase 5 → Phase 6.
- US1 and US2 are independent of each other (different tables/services) and can proceed in parallel after Phase 2; both touch `tasks.py` (T014, T021), so sequence those two edits.
- US3 needs data from both (T025 reads decisions and trade metrics) but its service tests use fixtures, so T023–T025 can start once Phase 2 is done; T029 UI needs T026.
- Within a story: tests → models/services → wiring → verification.

## Parallel Examples

- Phase 2: T002 ‖ T003 ‖ T006 (T004 after T002+T003).
- US1 tests: T007 ‖ T008 ‖ T009 ‖ T010.
- US1 vs US2: T011–T013 ‖ T019–T020.
- US3: T023 ‖ T024; T027 ‖ T028.

## Implementation Strategy

- **MVP = Phase 1–3 (US1)**: gate-value ledger with outcomes, inspectable via admin/shell — already answers "does this gate help?".
- Then US2 (R/MFE/MAE) so new trades accumulate excursion data early (it only records going forward, so ship it soon even before the UI).
- Then US3 for the page. Start collecting data as early as possible; diagnostics quality depends on elapsed time (≥ 24 h for full outcomes, ≥ 30 trades per row for non-flagged stats).

**Total tasks**: 35 — Setup 1, Foundational 5, US1 12, US2 4, US3 9, Polish 4.
