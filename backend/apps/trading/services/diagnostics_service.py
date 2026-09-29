"""Read-only diagnostics built from SignalDecision rows and closed Trades.

Shape is documented in specs/004-signal-decision-diagnostics/contracts/api.md.
Fields whose inputs are unavailable are None, never 0.
"""

from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from apps.trading.models import SignalDecision, Trade

from .excursion_service import compute_r_multiple

MIN_SAMPLE = 30
SCORE_BUCKET_SIZE = 10
FAVORABLE_R = 0.5  # a stopped trade that was at least this far in profit first
WINDOW_FIELDS = {"1h": "outcome_1h", "4h": "outcome_4h", "24h": "outcome_24h"}
STRUCTURAL_TAG_PREFIXES = ("grade:", "confidence:", "regime:")
MODES = {"paper", "live", "all"}


def _pct(part: int, whole: int) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _trade_r(trade: Trade) -> float | None:
    if trade.r_multiple is not None:
        return float(trade.r_multiple)
    derived = compute_r_multiple(trade)  # legacy trades: only when initial risk is known
    return float(derived) if derived is not None else None


def _trade_confidence(trade: Trade) -> int | None:
    value = (trade.replay_payload or {}).get("confidence_score")
    if value is None:
        for tag in trade.setup_tags or []:
            if str(tag).startswith("confidence:"):
                value = str(tag).split(":", 1)[1]
                break
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _trade_grade(trade: Trade) -> str:
    grade = (trade.replay_payload or {}).get("trade_grade")
    if not grade:
        for tag in trade.setup_tags or []:
            if str(tag).startswith("grade:"):
                grade = str(tag).split(":", 1)[1]
                break
    return str(grade).upper() if grade else "n/a"


def _trade_regime(trade: Trade) -> str:
    regime = (trade.replay_payload or {}).get("regime")
    if not regime:
        for tag in trade.setup_tags or []:
            if str(tag).startswith("regime:"):
                regime = str(tag).split(":", 1)[1]
                break
    return str(regime).upper() if regime else "UNKNOWN"


def _trade_row(label: str, trades: list[Trade]) -> dict:
    wins = sum(1 for t in trades if float(t.realized_pnl) > 0)
    r_values = [r for r in (_trade_r(t) for t in trades) if r is not None]
    avg_r = _mean(r_values)
    return {
        "label": label,
        "trades": len(trades),
        "win_rate": _pct(wins, len(trades)),
        "avg_r": avg_r,
        "expectancy_r": avg_r,  # mean R per trade == win% x avg win R + loss% x avg loss R
        "low_sample": len(trades) < MIN_SAMPLE,
    }


def _rows(groups: dict[str, list[Trade]], sort_by_label: bool = False) -> list[dict]:
    rows = [_trade_row(label, trades) for label, trades in groups.items()]
    if sort_by_label:
        return sorted(rows, key=lambda r: r["label"])
    return sorted(rows, key=lambda r: r["trades"], reverse=True)


def _gate_rows(decisions: list[SignalDecision], window: str) -> list[dict]:
    field = WINDOW_FIELDS[window]
    by_gate: dict[str, list[SignalDecision]] = defaultdict(list)
    for decision in decisions:
        by_gate[decision.result].append(decision)
    rows = []
    for gate, items in by_gate.items():
        resolved = [d for d in items if (getattr(d, field) or {}).get("status") == "resolved"]
        wins = losses = 0
        net_r = 0.0
        for d in resolved:
            hit = getattr(d, field).get("first_hit")
            if hit == "sl":
                losses += 1
                net_r += 1.0  # loss avoided: +1R saved
            elif hit == "tp1":
                wins += 1
                risk = abs(float(d.price) - float(d.ref_stop)) if d.ref_stop is not None else 0.0
                reward = abs(float(d.ref_tp1) - float(d.price)) if d.ref_tp1 is not None else 0.0
                net_r -= (reward / risk) if risk else 1.0  # win missed
        undecided = len(resolved) - wins - losses
        rows.append(
            {
                "gate": gate,
                "blocked": len(items),
                "resolved": len(resolved),
                "would_win_pct": _pct(wins, len(resolved)),
                "would_lose_pct": _pct(losses, len(resolved)),
                "undecided_pct": _pct(undecided, len(resolved)),
                "net_r": round(net_r, 2) if resolved else None,
                "low_sample": len(resolved) < MIN_SAMPLE,
            }
        )
    return sorted(rows, key=lambda r: r["blocked"], reverse=True)


def _exit_quality(trades: list[Trade]) -> dict:
    with_excursion = [t for t in trades if t.mfe_r is not None and t.mae_r is not None]
    giveback = [
        float(t.mfe_r) - r
        for t in with_excursion
        if (r := _trade_r(t)) is not None
    ]
    stopped = [t for t in with_excursion if "stop" in (t.close_reason or "").lower()]
    favorable_first = [t for t in stopped if float(t.mfe_r) >= FAVORABLE_R]
    winners = [t for t in with_excursion if float(t.realized_pnl) > 0]
    losers = [t for t in with_excursion if float(t.realized_pnl) < 0]
    return {
        "trades_with_excursion": len(with_excursion),
        "avg_giveback_r": _mean(giveback),
        "stopped_trades": len(stopped),
        "stopped_after_favorable_pct": _pct(len(favorable_first), len(stopped)),
        # Heat winners take before working: if this is well below 1R a tighter
        # stop would have kept them; if close to 1R the stop is already tight.
        "winners_avg_mae_r": _mean([float(t.mae_r) for t in winners]),
        "losers_avg_mfe_r": _mean([float(t.mfe_r) for t in losers]),
        "low_sample": len(with_excursion) < MIN_SAMPLE,
    }


def _bounds(start: date, end: date):
    tz = timezone.get_current_timezone()
    lo = timezone.make_aware(datetime.combine(start, time.min), tz)
    hi = timezone.make_aware(datetime.combine(end + timedelta(days=1), time.min), tz)
    return lo, hi


def build_diagnostics(user, start: date, end: date, mode: str = "all", window: str = "4h") -> dict:
    lo, hi = _bounds(start, end)
    trades_qs = Trade.objects.filter(
        user=user, status=Trade.Status.CLOSED, closed_at__gte=lo, closed_at__lt=hi
    )
    decisions_qs = SignalDecision.objects.filter(user=user, created_at__gte=lo, created_at__lt=hi)
    if mode in {"paper", "live"}:
        is_paper = mode == "paper"
        trades_qs = trades_qs.filter(is_paper=is_paper)
        decisions_qs = decisions_qs.filter(is_paper=is_paper)

    trades = list(trades_qs)
    decisions = list(decisions_qs)
    rejected = [d for d in decisions if d.result != SignalDecision.TAKEN]

    buckets: dict[str, list[Trade]] = defaultdict(list)
    grades: dict[str, list[Trade]] = defaultdict(list)
    tags: dict[str, list[Trade]] = defaultdict(list)
    regime_side: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        confidence = _trade_confidence(trade)
        if confidence is not None:
            low = confidence // SCORE_BUCKET_SIZE * SCORE_BUCKET_SIZE
            buckets[f"{low}-{low + SCORE_BUCKET_SIZE - 1}"].append(trade)
        grades[_trade_grade(trade)].append(trade)
        for tag in trade.setup_tags or []:
            if not str(tag).startswith(STRUCTURAL_TAG_PREFIXES):
                tags[str(tag)].append(trade)
        regime_side[f"{_trade_regime(trade)} / {trade.side}"].append(trade)

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "mode": mode,
        "window": window,
        "min_sample": MIN_SAMPLE,
        "gates": _gate_rows(rejected, window),
        "calibration": {
            "by_score_bucket": _rows(buckets, sort_by_label=True),
            "by_grade": _rows(grades, sort_by_label=True),
        },
        "expectancy": {
            "by_tag": _rows(tags)[:30],
            "by_regime_side": _rows(regime_side),
        },
        "exit_quality": _exit_quality(trades),
        "data_notes": {
            "decisions_total": len(decisions),
            "trades_total": len(trades),
            "excursion_granularity": "bot cycle (~20s)",
            "score_metric": "confidence score at entry",
        },
    }
