# Implementation Plan: Signal Decision Ledger & Trade Diagnostics

**Branch**: `004-signal-decision-diagnostics` | **Date**: 2026-09-29 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-signal-decision-diagnostics/spec.md`

## Summary

Add an append-only **SignalDecision** ledger written from the existing bot cycle (`process_config` in `backend/apps/trading/tasks.py`) at every entry-rejection point and at the entry-taken point, a Celery beat task that fills 1h/4h/24h forward outcomes from **real** exchange candles (never mock data), and new nullable fields on `Trade` (R-multiple, MFE, MAE) updated each cycle and finalized on close. A new read-only `GET /api/diagnostics` endpoint (new `diagnostics_service.py`, modeled on `analytics_service.py`) aggregates gate value, score/grade calibration, expectancy by tag and regime × side, and exit quality; a new `/diagnostics` Next.js page renders it. No entry/exit/sizing logic changes; every ledger write is wrapped so it cannot break a bot cycle.

## Technical Context

**Language/Version**: Python 3.11 / Django 5 (backend); TypeScript, Next.js 15, Tailwind 4 (frontend) — unchanged.

**Primary Dependencies**: DRF + SimpleJWT, Celery + beat, existing `BinanceService`. No new dependencies.

**Storage**: PostgreSQL (prod) / SQLite (local). One new table (`SignalDecision`), one migration adding nullable columns to `Trade`.

**Testing**: `pytest` under `backend/apps/trading/tests/` — gate-code mapping, dedupe, outcome resolution (fixture candles), excursion/R math, aggregation, per-user scoping, and "ledger failure does not break the cycle". Manual golden-path exercise of the page via `npm run dev`.

**Target Platform**: Existing Docker Compose stack; new Celery beat entry only.

**Project Type**: Web application (Next.js + Django).

**Performance Goals**: Diagnostics page < 3 s at 10k decisions / 1k trades (SC-005); ledger write adds < 5 ms per rejection and zero extra exchange calls in the bot cycle.

**Constraints**: No behavior change to trading (FR-008). No outcome computed from mock candles (Constitution V). Volume control: ~40 symbols × 20 s cycle means unbounded per-cycle logging is unacceptable — dedupe per signal candle (see research R2).

**Scale/Scope**: Only staff/master configs evaluate entries (followers mirror), so decisions are written for staff configs; followers still get trade metrics (R/MFE/MAE) and their own diagnostics for mirrored trades. Estimated tens of thousands of decision rows/day pre-prune, hence 90-day retention plus a "near-candidate" recording floor.

## Constitution Check

- **I. Paper-First Safety Gate** — PASS. Touches no order placement, credentials, or live flag. Outcome job uses public market data only; `is_paper` is copied to each decision so paper and live never mix.
- **II. Test-First for Trading Logic** — PASS with obligation. R/MFE/MAE math and rejection-to-gate mapping touch trading-adjacent code; tests are written first (tasks phase). Existing `test_signal.py`, `test_risk.py`, `test_paper_trading.py` must stay green (SC-006).
- **III. Risk & Position Discipline** — PASS. Recording calls sit beside existing `create_log`/`return` sites and never alter conditions or ordering. Excursion tracking is a read of price after the existing update step.
- **IV. Secure Credential Handling** — N/A. No secrets stored or logged.
- **V. Graceful Degradation & Observability** — PASS. Directly advances "gate rejections queryable" (structured, not text). `fetch_klines` silently falls back to mock data; the outcome job uses a real-data-only path so a market-data outage leaves outcomes `pending` instead of fabricating them. Ledger failures are caught and logged, never raised.
- **VI. Simplicity Across the Stack** — PASS. Extends `apps.trading` (model, service, task, view), the existing Celery beat schedule and the established `page.tsx` → `*-console.tsx` pattern. No new service/queue.

**Result**: No violations; Complexity Tracking not needed. Post-design re-check (after Phase 1): unchanged — PASS.

## Project Structure

### Documentation (this feature)

```text
specs/004-signal-decision-diagnostics/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── api.md
└── tasks.md            # created by /speckit-tasks
```

### Source Code (repository root)

```text
backend/apps/trading/
├── models.py                          # + SignalDecision; + Trade.r_multiple/mfe_*/mae_*
├── migrations/0045_signal_decision_and_trade_excursion.py
├── services/
│   ├── decision_ledger_service.py     # GateCode enum, record_decision(), dedupe, retention
│   ├── excursion_service.py           # update_excursion(trade, price), finalize_trade_metrics(trade)
│   ├── outcome_service.py             # resolve_outcomes(): real-klines forward simulation
│   ├── diagnostics_service.py         # build_diagnostics(user, start, end, mode)
│   ├── signal_service.py              # + SignalResult.blocked_gate (default None), set at internal hard gates
│   └── binance_service.py             # + fetch_klines_range(symbol, interval, start_ms, end_ms) real-only (returns None on failure)
├── tasks.py                           # ledger calls beside existing gates; excursion update; resolve_decision_outcomes + prune tasks
├── views.py / urls.py / serializers.py# DiagnosticsView at "diagnostics"
└── tests/
    ├── test_decision_ledger.py
    ├── test_excursion.py
    ├── test_outcome_service.py
    └── test_diagnostics_service.py
backend/config/settings.py             # + 2 CELERY_BEAT_SCHEDULE entries

frontend/
├── app/diagnostics/page.tsx
├── components/diagnostics/diagnostics-console.tsx
└── components/app-shell.tsx           # nav entry
```

**Structure Decision**: Extend the existing `apps.trading` app and mirror the `analytics` page/service pattern; no new Django app or frontend framework.

## Key Design Decisions (detail in [research.md](./research.md))

1. **Gate identifiers**: a `GateCode` enum in `decision_ledger_service.py`; each of the ~20 rejection sites in `process_config` gets one `record_rejection(...)` call next to its `create_log`. Internal hard gates in `score_signal` (RSI, MA25 zone, rejection candle, extended-move, etc.) surface via a new optional `SignalResult.blocked_gate` so they no longer exist only as text.
2. **Volume control**: unique key `(config, side, gate, signal_candle_ts)`; record only "near-candidates" (a directional score ≥ 60 % of the entry threshold, or any post-score gate rejection). Plain low-score `NO_TRADE` is not recorded.
3. **Outcomes**: beat task every 5 min; for each due window fetch real 1m/5m candles for the decision-to-window range; walk them to find max favorable/adverse move and first hit of would-be SL / TP1 (reference levels from the risk planner when available, else `1.5 × ATR` stop and `1R` TP1 stored on the row). Same-candle double touch → `ambiguous`.
4. **Excursion**: `update_excursion` runs each cycle right after the existing trade update in `process_config`, using cycle price (coarse but consistent); finalization on close reads the last values and computes `r_multiple = realized_pnl / initial_risk_amount` (initial risk = `|entry − initial_stop_loss| × quantity`). Documented limitation: intra-cycle wicks between 20 s cycles are missed.
5. **Diagnostics API**: single endpoint returning four sections; per-user scoped; date range + paper/live filter; low-sample flag computed server-side (n < 30).

## Risks

- **Mock-data fallback** in `fetch_klines` (mitigated by new real-only fetch).
- **Row growth** from rejections (mitigated by dedupe, floor, 90-day prune).
- **Excursion granularity** limited by 20 s cycles (accepted; stated in the UI footnote).
- Followers do not evaluate entries, so gate-value data reflects the master account's decisions only (stated in spec assumptions/UI).
