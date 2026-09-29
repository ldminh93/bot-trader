# Research: Signal Decision Ledger & Trade Diagnostics

## R1 — How to give rejections a stable gate identifier

- **Decision**: Add a `GateCode` enum; call `record_rejection(config, evaluation, GateCode.X)` immediately before each existing `return` in the entry section of `process_config` (circuit breaker, opposite-entry confirm, daily loss, max positions, ATR min, choppy/pullback regime, MA-stack in high volatility, tag/symbol auto-suppress, min confidence, ATR spike, funding, TF alignment, SL cooldown, volume spike, MA7 slope, entry location, margin, risk-limit). For hard gates inside `score_signal` add `blocked_gate: str | None = None` to `SignalResult`.
- **Rationale**: Today rejections are free text in `BotLog` (and `build_block_reason_stats` groups first-4 reason strings from snapshot payloads), so grouping is by prose. An enum makes grouping exact and survives message rewording.
- **Alternatives**: (a) parse log messages with regex — fragile, breaks on rewording; (b) refactor gates into a pipeline of gate objects — cleaner but a larger change to trading logic, violating "no behavior change" and Constitution III/VI; (c) wrap `create_log` — hides intent and mixes concerns.

## R2 — Preventing ledger explosion

- **Decision**: Uniqueness on `(config, side, gate, signal_candle_open_ts)` with insert-ignore; only record when a directional score is at least 60 % of the applicable entry threshold, or when a post-score gate rejected. Retention 90 days via daily prune task.
- **Rationale**: ~40 symbols × 3 cycles/min would produce ~170k rows/day if every evaluation were stored; per-candle dedupe (15m default) reduces this by ~45×, and the floor removes obvious non-candidates.
- **Alternatives**: store all evaluations (too large); sample 1-in-N (biases gate stats); store only counters (loses per-decision outcomes, the core value).

## R3 — Forward outcomes without fabricating data

- **Decision**: New `BinanceService.fetch_klines_range(symbol, interval, start_ms, end_ms)` that returns `None` on any HTTP/parse error (no mock fallback, no shared cache). Outcome task leaves the window `pending` on `None` and retries on the next run; after 48 h of pending it becomes `unavailable`.
- **Rationale**: `fetch_klines` returns `_mock_klines` on failure, which is correct for paper trading UX but would silently corrupt analytics.
- **Alternatives**: reuse `fetch_klines` and detect mock by a flag (mock output isn't tagged); store own candle history (heavy; `MarketSnapshot` is pruned at 7 days and is cycle-granular).

## R4 — Would-be SL/TP1 reference levels

- **Decision**: If the decision reached risk planning, store the planner's SL and TP1. Otherwise store defaults computed at decision time from ATR: SL = `1.5 × ATR`, TP1 = `1R`, and record `levels_source = "default"`. Diagnostics reports which level was hit first within the window (`tp1`/`sl`/`ambiguous`/`none`) and converts that to R saved/missed as defined below.
- **Rationale**: Most rejections happen before risk planning, so levels must be synthesized consistently. Storing them on the row makes outcomes reproducible.
- **Net R definition**: for a blocked decision, `would-lose` counts `+1R saved`, `would-win` counts `−(TP1 distance / SL distance) R missed`, `ambiguous/none` count 0.
- **Alternatives**: simulate the full exit ladder (TP2/TP3/trailing) — accurate but couples the analysis to exit logic that will keep changing.

## R5 — MFE/MAE and R tracking cadence

- **Decision**: Update inside `process_config` each cycle after the existing paper/live update step, using the cycle price; persist with `update_fields` only when a new extreme is reached. Finalize at close by reading the stored extremes and computing R from `realized_pnl` and initial risk.
- **Rationale**: One cheap write only when extremes change; no extra exchange calls; works for paper and live and for passive followers (they already refresh unrealized PnL each cycle).
- **Limitation**: Wicks between cycles (20 s) are missed. Acceptable for calibration; documented in UI footnote.
- **Alternatives**: recompute from 1m candles at close (more accurate, but extra API load and mock-fallback risk); compute in the paper/live services (touches trading code paths — rejected for FR-008).

## R6 — Diagnostics aggregation location and cost

- **Decision**: New `diagnostics_service.build_diagnostics` reading `Trade` (closed) and `SignalDecision` filtered by user/date/mode, aggregating in Python like `analytics_service.py`, with `only()` field selection; add index on `(user, created_at)` and `(user, gate, created_at)` for decisions.
- **Rationale**: Consistent with existing code; 10k decisions / 1k trades is trivially aggregated in-process within the 3 s budget.
- **Alternatives**: DB-level GROUP BY (more efficient but harder to express the calibration and low-sample logic; revisit if volume grows).

## R7 — Historical trades

- **Decision**: No backfill of MFE/MAE. R is computed lazily in diagnostics for older closed trades that have `initial_stop_loss` (falls back to unavailable if null/zero).
- **Rationale**: Past price paths aren't stored beyond `TradeSnapshot` cycle prices; guessing would violate "unavailable rather than zero".
