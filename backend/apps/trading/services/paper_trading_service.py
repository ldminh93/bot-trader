from decimal import Decimal

from django.utils import timezone

from apps.trading.models import Trade
from .discord_alert_service import send_trade_replay_export

TAKER_FEE_RATE = Decimal("0.0005")


def _apply_profit_steps(
    trade: Trade,
    price: Decimal,
    atr: float,
    trailing_multiplier: float,
    early_breakeven_r: float = 0,
    lock_profit_r: float = 0,
) -> bool:
    """
    Apply stepped profit-protection SL moves. Mutates trade.stop_loss and step flags.
    Returns True if stop_loss changed.

    Steps (each only ever tightens the SL):
      1. early_breakeven_r  — halve initial risk when price reaches N×R from entry
      2. 1R                 — move SL to breakeven
      3. lock_profit_r      — lock in (lock_profit_r − 1)R of profit
      4. ATR trailing       — trail from breakeven onward (not just after TP1)
    """
    initial_sl = trade.initial_stop_loss if trade.initial_stop_loss is not None else trade.stop_loss
    one_r = abs(trade.entry_price - initial_sl)
    if one_r == 0:
        return False
    is_long = trade.side == Trade.Side.LONG
    old_sl = trade.stop_loss

    # Step 1: early risk reduction
    if early_breakeven_r > 0 and not trade.early_breakeven_moved:
        eb_r = Decimal(str(early_breakeven_r))
        eb_target = trade.entry_price + (one_r * eb_r if is_long else -(one_r * eb_r))
        if (is_long and price >= eb_target) or (not is_long and price <= eb_target):
            midpoint = (initial_sl + trade.entry_price) / 2
            trade.stop_loss = max(trade.stop_loss, midpoint) if is_long else min(trade.stop_loss, midpoint)
            trade.early_breakeven_moved = True

    # Step 2: full breakeven at 1R
    if not trade.breakeven_moved:
        be_target = trade.entry_price + (one_r if is_long else -one_r)
        if (is_long and price >= be_target) or (not is_long and price <= be_target):
            trade.stop_loss = max(trade.stop_loss, trade.entry_price) if is_long else min(trade.stop_loss, trade.entry_price)
            trade.breakeven_moved = True

    # Step 3: lock partial profit
    if lock_profit_r > 0 and not trade.profit_lock_moved and trade.breakeven_moved:
        lp_r = Decimal(str(lock_profit_r))
        lp_target = trade.entry_price + (one_r * lp_r if is_long else -(one_r * lp_r))
        if (is_long and price >= lp_target) or (not is_long and price <= lp_target):
            locked = one_r * (lp_r - Decimal("1"))
            lock_sl = trade.entry_price + (locked if is_long else -locked)
            trade.stop_loss = max(trade.stop_loss, lock_sl) if is_long else min(trade.stop_loss, lock_sl)
            trade.profit_lock_moved = True

    # Step 4: ATR trailing — starts at breakeven (was: only after TP1)
    trail_distance = Decimal(str(atr)) * Decimal(str(trailing_multiplier))
    if trade.breakeven_moved and trail_distance > 0:
        trade.stop_loss = (
            max(trade.stop_loss, price - trail_distance) if is_long
            else min(trade.stop_loss, price + trail_distance)
        )

    return trade.stop_loss != old_sl


class PaperTradingService:
    @staticmethod
    def scale_in_entry(trade: Trade, price: float, additional_quantity: Decimal) -> None:
        """Add to an open partial position and mark the position as fully entered."""
        entry = Decimal(str(price))
        fee = entry * additional_quantity * TAKER_FEE_RATE
        trade.quantity += additional_quantity
        trade.remaining_quantity += additional_quantity
        trade.realized_pnl -= fee
        trade.fees += fee
        trade.partial_entry_filled = True
        trade.save()

    @staticmethod
    def open_trade(
        user,
        config,
        side: str,
        price: float,
        plan,
        reason: str,
        setup_tags: list[str] | None = None,
        leverage: int | None = None,
        replay_payload: dict | None = None,
        quantity_override: Decimal | None = None,
    ) -> Trade:
        quantity = Decimal(str(quantity_override if quantity_override is not None else plan.quantity))
        entry = Decimal(str(price))
        fee = entry * quantity * TAKER_FEE_RATE
        return Trade.objects.create(
            user=user,
            symbol=config.symbol,
            side=side,
            entry_price=entry,
            quantity=quantity,
            remaining_quantity=quantity,
            leverage=leverage or config.leverage,
            stop_loss=Decimal(str(plan.stop_loss)),
            initial_stop_loss=Decimal(str(plan.stop_loss)),
            take_profit_1=Decimal(str(plan.take_profit_1)),
            take_profit_2=Decimal(str(plan.take_profit_2)),
            take_profit_3=Decimal(str(plan.take_profit_3)),
            fees=fee,
            realized_pnl=-fee,
            open_reason=reason,
            setup_tags=setup_tags or [],
            replay_payload=replay_payload or {},
            is_paper=True,
            partial_entry_filled=(quantity_override is None),
        )

    @staticmethod
    def update_trade(
        trade: Trade,
        current_price: float,
        atr: float,
        trailing_multiplier: float,
        tp3_trailing_percent: float = 0,
        early_breakeven_r: float = 0,
        lock_profit_r: float = 0,
    ) -> Trade:
        price = Decimal(str(current_price))
        direction = Decimal("1") if trade.side == Trade.Side.LONG else Decimal("-1")
        raw_pnl = (price - trade.entry_price) * trade.remaining_quantity * direction
        trade.unrealized_pnl = raw_pnl
        margin_basis = PaperTradingService._margin_basis(trade)
        trade.pnl_percent = (
            (trade.realized_pnl + raw_pnl) / margin_basis * 100
            if margin_basis
            else 0
        )

        _apply_profit_steps(trade, price, atr, trailing_multiplier, early_breakeven_r, lock_profit_r)

        if not trade.tp1_hit and PaperTradingService._target_reached(trade, price, trade.take_profit_1):
            PaperTradingService._partial_close(trade, price, Decimal("0.30"))
            trade.tp1_hit = True
        if not trade.tp2_hit and PaperTradingService._target_reached(trade, price, trade.take_profit_2):
            PaperTradingService._partial_close(trade, price, Decimal("0.40"))
            trade.tp2_hit = True

        stop_hit = (
            trade.side == Trade.Side.LONG and price <= trade.stop_loss
        ) or (
            trade.side == Trade.Side.SHORT and price >= trade.stop_loss
        )

        # TP3: either start trailing or close immediately
        if not trade.tp3_hit and PaperTradingService._target_reached(trade, price, trade.take_profit_3):
            if tp3_trailing_percent > 0:
                trade.tp3_hit = True
                trade.tp3_trail_price = price
            else:
                PaperTradingService.close_trade(trade, price, "Take profit 3")
                return trade

        # Advance the TP3 trailing high-water mark and detect trail-stop
        tp3_trail_stop_hit = False
        if trade.tp3_hit and tp3_trailing_percent > 0:
            trail_pct = Decimal(str(tp3_trailing_percent)) / 100
            if trade.side == Trade.Side.LONG:
                if price > trade.tp3_trail_price:
                    trade.tp3_trail_price = price
                tp3_trail_stop_hit = price <= trade.tp3_trail_price * (1 - trail_pct)
            else:
                if price < trade.tp3_trail_price:
                    trade.tp3_trail_price = price
                tp3_trail_stop_hit = price >= trade.tp3_trail_price * (1 + trail_pct)

        if stop_hit or tp3_trail_stop_hit:
            PaperTradingService.close_trade(
                trade,
                price,
                "TP3 trailing stop" if tp3_trail_stop_hit else "Stop loss or trailing stop",
            )
        else:
            trade.save()
        return trade

    @staticmethod
    def close_trade(trade: Trade, price: Decimal, reason: str) -> Trade:
        PaperTradingService._partial_close(trade, price, Decimal("1"))
        trade.status = Trade.Status.CLOSED
        trade.exit_price = price
        trade.close_reason = reason
        trade.closed_at = timezone.now()
        trade.unrealized_pnl = 0
        margin_basis = PaperTradingService._margin_basis(trade)
        trade.pnl_percent = (
            trade.realized_pnl / margin_basis * 100
            if margin_basis
            else 0
        )
        trade.save()
        send_trade_replay_export(trade)
        return trade

    @staticmethod
    def _partial_close(trade: Trade, price: Decimal, fraction_of_original: Decimal) -> None:
        requested = trade.quantity * fraction_of_original
        closing_quantity = min(trade.remaining_quantity, requested)
        if closing_quantity <= 0:
            return
        direction = Decimal("1") if trade.side == Trade.Side.LONG else Decimal("-1")
        gross = (price - trade.entry_price) * closing_quantity * direction
        fee = price * closing_quantity * TAKER_FEE_RATE
        trade.realized_pnl += gross - fee
        trade.fees += fee
        trade.remaining_quantity -= closing_quantity

    @staticmethod
    def _target_reached(trade: Trade, price: Decimal, target: Decimal) -> bool:
        if trade.side == Trade.Side.LONG:
            return price >= target
        return price <= target

    @staticmethod
    def _margin_basis(trade: Trade) -> Decimal:
        if trade.leverage <= 0:
            return Decimal("0")
        return trade.entry_price * trade.quantity / Decimal(trade.leverage)
