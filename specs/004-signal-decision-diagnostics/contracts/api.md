# API Contract: Diagnostics

## GET /api/diagnostics

**Auth**: JWT, `IsAuthenticated`. Data is always scoped to `request.user`; no user parameter.

**Query params** (all optional)

| Param | Values | Default |
|-------|--------|---------|
| `start` | `YYYY-MM-DD` | 30 days ago |
| `end` | `YYYY-MM-DD` | today |
| `mode` | `paper` \| `live` \| `all` | `all` |
| `window` | `1h` \| `4h` \| `24h` | `4h` (which forward-outcome window gate value is judged on) |

**200 response**

```json
{
  "range": {"start": "2026-08-30", "end": "2026-09-29"},
  "mode": "all",
  "window": "4h",
  "min_sample": 30,
  "gates": [
    {
      "gate": "extended_move",
      "blocked": 120,
      "resolved": 96,
      "would_win_pct": 22.9,
      "would_lose_pct": 58.3,
      "undecided_pct": 18.8,
      "net_r": 31.5,
      "low_sample": false
    }
  ],
  "calibration": {
    "by_score_bucket": [{"label": "60-69", "trades": 14, "win_rate": 50.0, "avg_r": 0.42, "low_sample": true}],
    "by_grade": [{"label": "A", "trades": 9, "win_rate": 66.7, "avg_r": 0.9, "low_sample": true}]
  },
  "expectancy": {
    "by_tag": [{"label": "pullback", "trades": 40, "win_rate": 45.0, "avg_r": 0.31, "expectancy_r": 0.31, "low_sample": false}],
    "by_regime_side": [{"label": "TRENDING / SHORT", "trades": 22, "win_rate": 54.5, "avg_r": 0.5, "expectancy_r": 0.5, "low_sample": true}]
  },
  "exit_quality": {
    "trades_with_excursion": 58,
    "avg_giveback_r": 0.8,
    "stopped_trades": 30,
    "stopped_after_favorable_pct": 40.0,
    "winners_avg_mae_r": 0.4,
    "losers_avg_mfe_r": 0.3,
    "low_sample": false
  },
  "data_notes": {
    "decisions_total": 5321,
    "trades_total": 72,
    "excursion_granularity": "bot cycle (~20s)",
    "score_metric": "confidence score at entry"
  }
}
```

- Fields whose inputs are unavailable are `null`, never `0`.
- Stop-tightness evidence: `winners_avg_mae_r` is the average heat (MAE, in R) winners took before working — well below 1R means a tighter stop was viable; `losers_avg_mfe_r` is how far losers went in favor first. `stopped_after_favorable_pct` is the share of stopped trades that were at least +0.5R first.
- Gate `net_r`: +1R per blocked entry whose stop was reached first (loss avoided); −(reward ÷ risk) R per blocked entry whose TP1 was reached first (win missed); ambiguous/none count 0. `null` when nothing resolved.
- `by_score_bucket` buckets the entry **confidence score** in 10-point bands.
- Empty data returns all sections as empty arrays / nulls with `data_notes` totals of 0 (frontend shows the empty state).

**Errors**: `401` unauthenticated; `400` invalid date/mode/window with `{"detail": "..."}`.

## Existing endpoints

Trade serializer (`GET /api/trades`) gains read-only `r_multiple`, `mfe_r`, `mae_r`, `mfe_pct`, `mae_pct` (nullable). No other existing contract changes.
