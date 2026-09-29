# Quickstart: Validating Signal Decision Ledger & Diagnostics

## Prerequisites

- Backend and Celery worker + beat running (`docker compose up`), paper mode (default; `ENABLE_LIVE_TRADING` unset).
- At least one admin (staff) account with a running bot on 2+ symbols. Followers do not evaluate entries.
- Migration applied: `python manage.py migrate`.

## 1. Automated checks

```bash
cd backend
pytest apps/trading/tests/test_decision_ledger.py apps/trading/tests/test_excursion.py \
       apps/trading/tests/test_outcome_service.py apps/trading/tests/test_diagnostics_service.py
pytest            # full suite: existing trading tests must remain green (SC-006)
```

Expected: all pass; no change in `test_signal.py` / `test_risk.py` / `test_paper_trading.py` results.

## 2. Ledger records rejections and takes (US1)

1. Let the bot run for ~10 minutes.
2. In a Django shell: `SignalDecision.objects.values("result").annotate(n=Count("id"))`.
3. Expect rows for named gates (not free text) plus `TAKEN` for any opened trade, and no duplicate `(config, side, result, signal_candle_ts)`.

## 3. Outcomes resolve from real data (US1)

1. After 1 h, run `resolve_decision_outcomes` (or wait for beat).
2. Expect `outcome_1h.status == "resolved"` with `first_hit` in `tp1|sl|ambiguous|none`.
3. Block network access to Binance and rerun: rows stay `pending` (no values fabricated).

## 4. R / MFE / MAE on trades (US2)

1. Open and close a paper trade (or use an existing closed one opened after deploy).
2. `GET /api/trades` shows `r_multiple`, `mfe_r`, `mae_r`; verify by hand: `r_multiple ≈ realized_pnl / (|entry − initial_stop_loss| × quantity)`.
3. Older trades show `null` MFE/MAE.

## 5. Diagnostics page (US3)

1. `npm run dev` in `frontend/`, log in, open `/diagnostics`.
2. Confirm four sections render, rows with n < 30 show a low-sample badge, date/mode filters refresh all sections, a brand-new user sees the empty state.
3. Log in as a second user and confirm none of the first user's data appears.

## 6. Safety regression

- Compare a paper session before/after: same entries/exits for identical inputs (existing tests cover this).
- Force `record_decision` to raise (test hook) and confirm the bot cycle still completes and logs an error.
