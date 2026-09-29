"""Per-trade excursion (MFE/MAE) and R-multiple tracking.

Diagnostics only. Every function is exception-safe: a failure here must never
interrupt a bot cycle or a trade close.
"""

import logging
from decimal import Decimal

from apps.trading.models import Trade

logger = logging.getLogger(__name__)


def _dec(value: float, places: int) -> Decimal:
    return Decimal(str(round(value, places)))


def _risk_per_unit(trade: Trade) -> float | None:
    if trade.initial_stop_loss is None:
        return None
    distance = abs(float(trade.entry_price) - float(trade.initial_stop_loss))
    return distance if distance > 0 else None


def compute_excursion(trade: Trade, price: float) -> tuple[float, float]:
    """(favorable, adverse) price distance from entry, both >= 0."""
    move = float(price) - float(trade.entry_price)
    if trade.side == Trade.Side.SHORT:
        move = -move
    return max(move, 0.0), max(-move, 0.0)


def update_excursion(trade: Trade, price) -> bool:
    """Extend the trade's best/worst excursion with ``price``.

    Writes only when a new extreme is reached. Returns True if it saved.
    """
    try:
        entry = float(trade.entry_price)
        if entry <= 0 or price is None:
            return False
        favorable, adverse = compute_excursion(trade, float(price))
        risk = _risk_per_unit(trade)
        fields: list[str] = []

        cur_mfe = float(trade.mfe_pct) if trade.mfe_pct is not None else None
        cur_mae = float(trade.mae_pct) if trade.mae_pct is not None else None
        fav_pct = favorable / entry * 100
        adv_pct = adverse / entry * 100
        if cur_mfe is None or fav_pct > cur_mfe:
            trade.mfe_pct = _dec(fav_pct, 6)
            fields.append("mfe_pct")
            if risk:
                trade.mfe_r = _dec(favorable / risk, 4)
                fields.append("mfe_r")
        if cur_mae is None or adv_pct > cur_mae:
            trade.mae_pct = _dec(adv_pct, 6)
            fields.append("mae_pct")
            if risk:
                trade.mae_r = _dec(adverse / risk, 4)
                fields.append("mae_r")
        if not fields:
            return False
        Trade.objects.filter(pk=trade.pk).update(**{f: getattr(trade, f) for f in fields})
        return True
    except Exception:
        logger.exception("Excursion update failed for trade %s", getattr(trade, "pk", "?"))
        return False


def compute_r_multiple(trade: Trade) -> Decimal | None:
    """realized_pnl relative to the initial risk amount; None if unavailable."""
    risk = _risk_per_unit(trade)
    quantity = float(trade.quantity or 0)
    if risk is None or quantity <= 0:
        return None
    return _dec(float(trade.realized_pnl) / (risk * quantity), 4)


def finalize_trade_metrics(trade: Trade) -> None:
    """Idempotently store the final excursion (including the exit price) and R."""
    try:
        if trade.status != Trade.Status.CLOSED:
            return
        if trade.exit_price is not None:
            update_excursion(trade, float(trade.exit_price))
        r_multiple = compute_r_multiple(trade)
        if r_multiple != trade.r_multiple:
            trade.r_multiple = r_multiple
            Trade.objects.filter(pk=trade.pk).update(r_multiple=r_multiple)
    except Exception:
        logger.exception("Finalizing trade metrics failed for trade %s", getattr(trade, "pk", "?"))
