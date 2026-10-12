"""Stop × target sweep over recorded SignalDecision outcomes.

Each resolved outcome window stores the best (max_fav_pct) and worst
(max_adv_pct) move from the decision price. Replaying those against a grid of
stop distances (in ATR) and targets (in R of that stop) shows which level pair
would have produced the best win rate and expectancy, without new data.

Limits, surfaced to the UI:
- Only extremes are stored, not their order. When a window reached both the
  stop and the target the result is unknown ("ambiguous"); the cell reports
  its share and a worst-case expectancy that counts every ambiguous one as a loss.
- Windows that reached neither level are "open" and excluded from win rate and
  expectancy (their close price is not stored). Longer windows leave fewer open.
"""

from collections import defaultdict
from datetime import date

from apps.trading.models import SignalDecision

from .decision_ledger_service import DEFAULT_LEVEL_ATR
from .diagnostics_service import MIN_SAMPLE, WINDOW_FIELDS, _bounds, _mean, _pct
from .paper_trading_service import TAKER_FEE_RATE

STOPS_ATR = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5)
TARGETS_R = (0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0)
ROUND_TRIP_FEE_PCT = float(TAKER_FEE_RATE) * 2 * 100  # entry + exit taker fill, % of notional
MAX_AMBIGUOUS_FOR_BEST = 25.0  # a cell this uncertain cannot be called "best"
POPULATIONS = {"all", "taken"}


def decision_atr(decision: SignalDecision) -> float | None:
    """Stored ATR, or the one implied by default reference levels (1.5 ATR stop)."""
    if decision.atr is not None and float(decision.atr) > 0:
        return float(decision.atr)
    if decision.levels_source == "default" and decision.ref_stop is not None:
        distance = abs(float(decision.price) - float(decision.ref_stop))
        return distance / DEFAULT_LEVEL_ATR if distance > 0 else None
    return None


def classify(max_fav_pct: float, max_adv_pct: float, stop_pct: float, target_pct: float) -> str:
    hit_stop = max_adv_pct >= stop_pct
    hit_target = max_fav_pct >= target_pct
    if hit_stop and hit_target:
        return "ambiguous"
    if hit_stop:
        return "loss"
    if hit_target:
        return "win"
    return "open"


def _samples(decisions: list[SignalDecision], field: str) -> tuple[list[tuple[float, float, float]], int]:
    """[(atr_pct, max_fav_pct, max_adv_pct)] for resolved windows, plus how many lacked ATR."""
    samples = []
    no_atr = 0
    for d in decisions:
        outcome = getattr(d, field) or {}
        if outcome.get("status") != "resolved" or "max_fav_pct" not in outcome:
            continue
        atr = decision_atr(d)
        price = float(d.price)
        if atr is None or price <= 0:
            no_atr += 1
            continue
        samples.append((atr / price * 100, float(outcome["max_fav_pct"]), float(outcome["max_adv_pct"])))
    return samples, no_atr


def _cell(stop_atr: float, target_r: float, samples: list[tuple[float, float, float]]) -> dict:
    counts: dict[str, int] = defaultdict(int)
    decided_r: list[float] = []
    worst_r: list[float] = []
    for atr_pct, fav, adv in samples:
        stop_pct = stop_atr * atr_pct
        fee_r = ROUND_TRIP_FEE_PCT / stop_pct if stop_pct > 0 else 0.0
        outcome = classify(fav, adv, stop_pct, target_r * stop_pct)
        counts[outcome] += 1
        if outcome == "win":
            decided_r.append(target_r - fee_r)
            worst_r.append(target_r - fee_r)
        elif outcome == "loss":
            decided_r.append(-1.0 - fee_r)
            worst_r.append(-1.0 - fee_r)
        elif outcome == "ambiguous":
            worst_r.append(-1.0 - fee_r)
    decided = counts["win"] + counts["loss"]
    total = len(samples)
    expectancy = _mean(decided_r)
    worst = _mean(worst_r)
    return {
        "stop_atr": stop_atr,
        "target_r": target_r,
        "samples": total,
        "decided": decided,
        "win_rate": _pct(counts["win"], decided),
        "ambiguous_pct": _pct(counts["ambiguous"], total),
        "open_pct": _pct(counts["open"], total),
        "expectancy_r": round(expectancy, 3) if expectancy is not None else None,
        "worst_case_r": round(worst, 3) if worst is not None else None,
        "low_sample": decided < MIN_SAMPLE,
    }


def _best(cells: list[dict]) -> dict | None:
    eligible = [
        c for c in cells
        if not c["low_sample"]
        and c["expectancy_r"] is not None
        and (c["ambiguous_pct"] or 0) <= MAX_AMBIGUOUS_FOR_BEST
    ]
    if not eligible:
        return None
    best = max(eligible, key=lambda c: c["expectancy_r"])
    return {"stop_atr": best["stop_atr"], "target_r": best["target_r"]}


def build_level_sweep(
    user, start: date, end: date, mode: str = "all", window: str = "24h", population: str = "all"
) -> dict:
    lo, hi = _bounds(start, end)
    qs = SignalDecision.objects.filter(user=user, created_at__gte=lo, created_at__lt=hi)
    if mode in {"paper", "live"}:
        qs = qs.filter(is_paper=mode == "paper")
    if population == "taken":
        qs = qs.filter(result=SignalDecision.TAKEN)
    field = WINDOW_FIELDS[window]
    samples, no_atr = _samples(list(qs.only("price", "atr", "levels_source", "ref_stop", field)), field)
    cells = [_cell(s, t, samples) for s in STOPS_ATR for t in TARGETS_R]
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "mode": mode,
        "window": window,
        "population": population,
        "min_sample": MIN_SAMPLE,
        "stops_atr": list(STOPS_ATR),
        "targets_r": list(TARGETS_R),
        "fee_round_trip_pct": ROUND_TRIP_FEE_PCT,
        "samples": len(samples),
        "skipped_no_atr": no_atr,
        "cells": cells,
        "best": _best(cells),
    }
