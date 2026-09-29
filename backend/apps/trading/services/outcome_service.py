"""Forward outcomes for SignalDecision rows (what did the market do after?).

Uses real exchange candles only (BinanceService.fetch_klines_range). If the
data can't be fetched the window stays ``pending`` and is retried; it becomes
``unavailable`` once it has been overdue for UNAVAILABLE_AFTER_HOURS.
"""

import logging
from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from apps.trading.models import SignalDecision

from .binance_service import BinanceService

logger = logging.getLogger(__name__)

# outcome field -> (window seconds, candle interval used to walk the window)
WINDOWS = {
    "outcome_1h": (3600, "1m"),
    "outcome_4h": (4 * 3600, "1m"),
    "outcome_24h": (24 * 3600, "5m"),
}
UNAVAILABLE_AFTER_HOURS = 48
MAX_DECISIONS_PER_RUN = 1500


def evaluate_window(side: str, price: float, stop, tp1, candles: list[dict]) -> dict:
    """Walk candles (oldest first) and describe the window.

    max_fav_pct / max_adv_pct: best / worst move against ``price`` over the
    whole window (both >= 0, percent). first_hit: which reference level was
    touched first: 'tp1' | 'sl' | 'ambiguous' (both inside one candle) |
    'none' | 'no_levels'.
    """
    is_long = side == "LONG"
    max_fav = 0.0
    max_adv = 0.0
    first_hit = None
    for candle in candles:
        high, low = float(candle["high"]), float(candle["low"])
        fav = (high - price) if is_long else (price - low)
        adv = (price - low) if is_long else (high - price)
        max_fav = max(max_fav, fav)
        max_adv = max(max_adv, adv)
        if first_hit is None and stop is not None and tp1 is not None:
            hit_sl = low <= float(stop) if is_long else high >= float(stop)
            hit_tp = high >= float(tp1) if is_long else low <= float(tp1)
            if hit_sl and hit_tp:
                first_hit = "ambiguous"
            elif hit_sl:
                first_hit = "sl"
            elif hit_tp:
                first_hit = "tp1"
    if stop is None or tp1 is None:
        first_hit = "no_levels"
    return {
        "status": "resolved",
        "max_fav_pct": round(max_fav / price * 100, 4) if price else 0.0,
        "max_adv_pct": round(max_adv / price * 100, 4) if price else 0.0,
        "first_hit": first_hit or "none",
        "resolved_at": timezone.now().isoformat(),
    }


def _due_windows(decision: SignalDecision, now):
    for field, (seconds, interval) in WINDOWS.items():
        outcome = getattr(decision, field) or {}
        if outcome.get("status") in {"resolved", "unavailable"}:
            continue
        end = decision.created_at + timedelta(seconds=seconds)
        if end <= now:
            yield field, end, interval


def resolve_outcomes(now=None, client: BinanceService | None = None) -> dict:
    """Resolve every due, unresolved window. Returns counters for logging/tests."""
    now = now or timezone.now()
    client = client or BinanceService()
    oldest = now - timedelta(seconds=WINDOWS["outcome_24h"][0] + UNAVAILABLE_AFTER_HOURS * 3600)
    decisions = list(
        SignalDecision.objects.filter(created_at__gte=oldest).order_by("created_at")[:MAX_DECISIONS_PER_RUN]
    )
    work: dict[tuple[str, str], list] = defaultdict(list)
    for decision in decisions:
        for field, end, interval in _due_windows(decision, now):
            work[(decision.symbol, interval)].append((decision, field, end))

    counts = {"resolved": 0, "pending": 0, "unavailable": 0}
    for (symbol, interval), items in work.items():
        start_ms = int(min(d.created_at for d, _, _ in items).timestamp() * 1000)
        end_ms = int(max(e for _, _, e in items).timestamp() * 1000)
        candles = client.fetch_klines_range(symbol, interval, start_ms, end_ms)
        for decision, field, end in items:
            if not candles:
                overdue = now - end > timedelta(hours=UNAVAILABLE_AFTER_HOURS)
                status = "unavailable" if overdue else "pending"
                setattr(decision, field, {"status": status})
                decision.save(update_fields=[field])
                counts[status] += 1
                continue
            d_ms = int(decision.created_at.timestamp() * 1000)
            e_ms = int(end.timestamp() * 1000)
            window = [c for c in candles if d_ms <= c["timestamp"] <= e_ms]
            if not window:
                setattr(decision, field, {"status": "pending"})
                decision.save(update_fields=[field])
                counts["pending"] += 1
                continue
            outcome = evaluate_window(
                decision.side, float(decision.price), decision.ref_stop, decision.ref_tp1, window
            )
            setattr(decision, field, outcome)
            decision.save(update_fields=[field])
            counts["resolved"] += 1
    return counts
