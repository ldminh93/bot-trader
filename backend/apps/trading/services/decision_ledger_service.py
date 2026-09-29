"""Append-only ledger of entry decisions (taken or rejected by a named gate).

Diagnostics only: nothing here may change trading behaviour, and every public
``record_*`` function swallows its own errors so a ledger problem can never
interrupt a bot cycle.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.trading.models import SignalDecision

from .gate_codes import GateCode

logger = logging.getLogger(__name__)

__all__ = [
    "GateCode",
    "NEAR_CANDIDATE_FLOOR",
    "DECISION_RETENTION_DAYS",
    "default_reference_levels",
    "prune_old_decisions",
    "record_rejection",
    "record_taken",
]

# A score-level rejection is only worth storing when the candidate was at
# least this fraction of the way to the entry threshold; otherwise every idle
# symbol would write a row each candle.
NEAR_CANDIDATE_FLOOR = 0.6
DECISION_RETENTION_DAYS = 90
# Stop/first-target distance (in ATR) assumed for decisions that never reached
# risk planning, so their forward outcome is still measurable and reproducible.
DEFAULT_LEVEL_ATR = 1.5


def _threshold_for(config, side: str) -> int:
    if side == "SHORT":
        return int(getattr(config, "short_entry_score_threshold", 0) or config.entry_score_threshold)
    return int(config.entry_score_threshold)


def _is_paper(config) -> bool:
    return not (config.live_mode_requested and settings.ENABLE_LIVE_TRADING)


def _candle_ts(evaluation) -> int:
    candles = getattr(evaluation.indicators, "candles", None) or []
    if not candles:
        return 0
    try:
        return int(candles[-1].get("timestamp") or 0)
    except (TypeError, ValueError):
        return 0


def default_reference_levels(side: str, price: float, atr: float | None):
    """(stop, tp1, source) using DEFAULT_LEVEL_ATR × ATR for both distances (1R target)."""
    if not atr or atr <= 0 or price <= 0:
        return None, None, "none"
    distance = atr * DEFAULT_LEVEL_ATR
    if side == "LONG":
        return price - distance, price + distance, "default"
    return price + distance, price - distance, "default"


def _candidate_side_and_score(signal) -> tuple[str | None, int]:
    if signal.signal in {"LONG", "SHORT"}:
        score = signal.long_score if signal.signal == "LONG" else signal.short_score
        return signal.signal, int(score)
    if signal.short_score > 0:
        return "SHORT", int(signal.short_score)
    if signal.long_score > 0:
        return "LONG", int(signal.long_score)
    return None, 0


def _store(config, evaluation, *, side, score, result, trade=None, stop=None, tp1=None, source=None):
    payload = evaluation.snapshot.payload or {}
    price = float(evaluation.metrics["price"])
    if stop is None or tp1 is None:
        stop, tp1, source = default_reference_levels(
            side, price, getattr(evaluation.indicators, "atr", None)
        )
    candle_ts = _candle_ts(evaluation)
    defaults = {
        "user": config.user,
        "symbol": config.symbol,
        "is_paper": _is_paper(config),
        "score": score,
        "confidence": int(payload.get("confidence_score", 0) or 0),
        "grade": str(payload.get("trade_grade", "") or "")[:2],
        "regime": str(payload.get("regime", "") or "")[:24],
        "setup_tags": list(payload.get("setup_tags", []) or []),
        "price": price,
        "ref_stop": stop,
        "ref_tp1": tp1,
        "levels_source": source or "none",
        "trade": trade,
    }
    try:
        with transaction.atomic():
            decision, created = SignalDecision.objects.get_or_create(
                config=config,
                side=side,
                result=result,
                signal_candle_ts=candle_ts,
                defaults=defaults,
            )
    except IntegrityError:
        return None
    if not created and trade is not None and decision.trade_id is None:
        decision.trade = trade
        decision.save(update_fields=["trade"])
    return decision


def record_rejection(config, evaluation, gate: str, *, side: str | None = None) -> SignalDecision | None:
    """Store a rejected candidate. Never raises; returns None when skipped."""
    try:
        if not config.user.is_staff:
            return None
        cand_side, score = _candidate_side_and_score(evaluation.signal)
        side = side or cand_side
        if side is None:
            return None
        # Post-score gates always matter (the signal itself passed scoring);
        # score-level gates need a near-candidate to be worth a row.
        if evaluation.signal.signal == "NO_TRADE":
            if score < NEAR_CANDIDATE_FLOOR * _threshold_for(config, side):
                return None
        return _store(config, evaluation, side=side, score=score, result=gate)
    except Exception:
        logger.exception("Decision ledger: failed to record rejection %s for %s", gate, getattr(config, "symbol", "?"))
        return None


def record_taken(config, evaluation, trade, plan=None) -> SignalDecision | None:
    """Store an accepted entry linked to its trade. Never raises."""
    try:
        side = evaluation.signal.signal
        if side not in {"LONG", "SHORT"}:
            return None
        _, score = _candidate_side_and_score(evaluation.signal)
        stop = tp1 = source = None
        if plan is not None:
            stop, tp1, source = float(plan.stop_loss), float(plan.take_profit_1), "planner"
        return _store(
            config, evaluation, side=side, score=score, result=SignalDecision.TAKEN,
            trade=trade, stop=stop, tp1=tp1, source=source,
        )
    except Exception:
        logger.exception("Decision ledger: failed to record taken entry for %s", getattr(config, "symbol", "?"))
        return None


def prune_old_decisions(now=None, retention_days: int = DECISION_RETENTION_DAYS) -> int:
    cutoff = (now or timezone.now()) - timedelta(days=retention_days)
    deleted, _ = SignalDecision.objects.filter(created_at__lt=cutoff).delete()
    return deleted
