# Data Model: Signal Decision Ledger & Trade Diagnostics

## SignalDecision (new, `apps.trading`)

| Field | Type | Notes |
|-------|------|-------|
| user | FK → User (CASCADE) | Owner; all reads filter on it |
| config | FK → TradingBotConfig (SET_NULL, null) | Bot that evaluated |
| symbol | Char(24) | |
| side | Char(8) | LONG / SHORT candidate |
| result | Char(40) | `TAKEN` or a `GateCode` value |
| is_paper | Bool | Copied from config mode at decision time |
| score | SmallInt | Directional score for `side` |
| confidence | SmallInt | From snapshot payload |
| grade | Char(2) | A–D |
| regime | Char(24) | From snapshot payload |
| setup_tags | JSON list | Snapshot tags (for tag analysis of blocked setups) |
| price | Decimal(24,10) | Price at decision |
| ref_stop | Decimal, null | Would-be SL |
| ref_tp1 | Decimal, null | Would-be first TP |
| levels_source | Char(12) | `planner` / `default` / `none` |
| signal_candle_ts | BigInt | Open time (ms) of last closed signal candle; dedupe key |
| trade | FK → Trade (SET_NULL, null) | Set when `result == TAKEN` |
| outcome_1h / outcome_4h / outcome_24h | JSON | `{status, max_fav_pct, max_adv_pct, first_hit, resolved_at}` |
| created_at | DateTime, indexed | |

- `status`: `pending` → `resolved` \| `unavailable`
- `first_hit`: `tp1` \| `sl` \| `ambiguous` \| `none`

**Constraints/Indexes**: unique `(config, side, result, signal_candle_ts)`; index `(user, -created_at)`; index `(user, result, -created_at)`; index on `created_at` for prune and outcome scans.

**Lifecycle**: created at decision → windows resolve independently as they elapse (never overwritten once `resolved`) → deleted by prune after 90 days.

## Trade (extended)

| Field | Type | Notes |
|-------|------|-------|
| r_multiple | Decimal(12,4), null | Set on close: `realized_pnl / (|entry − initial_stop_loss| × quantity)`; null if initial risk missing/zero |
| mfe_pct / mae_pct | Decimal(12,6), null | Best/worst price excursion since entry, % of entry, sign-normalized so MFE ≥ 0, MAE ≥ 0 |
| mfe_r / mae_r | Decimal(12,4), null | Same excursions in multiples of initial risk per unit |

All nullable, no default backfill → "unavailable", never zero.

## Diagnostics Summary (not stored)

Computed per request; shape in [contracts/api.md](./contracts/api.md).

## GateCode (`backend/apps/trading/services/gate_codes.py`)

Stable strings persisted in `SignalDecision.result` — never rename, only add.

| Group | Codes | Source |
|-------|-------|--------|
| Score-level hard gates | `ma_alignment`, `macro_direction`, `extended_move`, `rsi_oversold`, `pullback_zone`, `rejection_candle`, `entry_location`, `below_score_threshold` | `signal_service.score_signal` via `SignalResult.blocked_gate` |
| Confirmation filters | `sideway_block`, `trend_alignment`, `htf_confirm`, `bias_4h`, `oi_confirm`, `volume_confirm`, `ma7_slope_confirm`, `funding_confirm` | `market_snapshot_service` (converts a scored signal to NO_TRADE) |
| Cycle-level gates | `circuit_breaker`, `opposite_unconfirmed`, `daily_loss`, `max_positions`, `atr_min`, `regime_choppy`, `reversal_high_vol`, `suppressed_tag`, `suppressed_symbol`, `min_confidence`, `atr_spike`, `funding`, `tf_alignment`, `sl_cooldown`, `volume_spike`, `ma7_slope`, `margin_insufficient`, `risk_limit`, `existing_position`, `exchange_position` | `tasks.process_config` |

`taken` (not a gate) marks an accepted entry.
