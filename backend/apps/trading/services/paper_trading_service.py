from decimal import Decimal

from django.utils import timezone

from apps.trading.models import Trade

TAKER_FEE_RATE = Decimal("0.0005")


class PaperTradingService:
    @staticmethod
    def open_trade(user, config, side: str, price: float, plan, reason: str) -> Trade:
        quantity = Decimal(str(plan.quantity))
        entry = Decimal(str(price))
        fee = entry * quantity * TAKER_FEE_RATE
        return Trade.objects.create(
            user=user,
            symbol=config.symbol,
            side=side,
            entry_price=entry,
            quantity=quantity,
            remaining_quantity=quantity,
            leverage=config.leverage,
            stop_loss=Decimal(str(plan.stop_loss)),
            take_profit_1=Decimal(str(plan.take_profit_1)),
            take_profit_2=Decimal(str(plan.take_profit_2)),
            take_profit_3=Decimal(str(plan.take_profit_3)),
            fees=fee,
            realized_pnl=-fee,
            open_reason=reason,
            is_paper=True,
        )

    @staticmethod
    def update_trade(trade: Trade, current_price: float, atr: float, trailing_multiplier: float) -> Trade:
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
        one_r = abs(trade.entry_price - trade.stop_loss)

        if not trade.breakeven_moved and (
            (trade.side == Trade.Side.LONG and price >= trade.entry_price + one_r)
            or (trade.side == Trade.Side.SHORT and price <= trade.entry_price - one_r)
        ):
            trade.stop_loss = trade.entry_price
            trade.breakeven_moved = True

        if not trade.tp1_hit and PaperTradingService._target_reached(trade, price, trade.take_profit_1):
            PaperTradingService._partial_close(trade, price, Decimal("0.30"))
            trade.tp1_hit = True
        if not trade.tp2_hit and PaperTradingService._target_reached(trade, price, trade.take_profit_2):
            PaperTradingService._partial_close(trade, price, Decimal("0.40"))
            trade.tp2_hit = True

        trail_distance = Decimal(str(atr)) * Decimal(str(trailing_multiplier))
        if trade.tp1_hit and trail_distance > 0:
            if trade.side == Trade.Side.LONG:
                trade.stop_loss = max(trade.stop_loss, price - trail_distance)
            else:
                trade.stop_loss = min(trade.stop_loss, price + trail_distance)

        stop_hit = (
            trade.side == Trade.Side.LONG and price <= trade.stop_loss
        ) or (
            trade.side == Trade.Side.SHORT and price >= trade.stop_loss
        )
        tp3_hit = PaperTradingService._target_reached(trade, price, trade.take_profit_3)
        if stop_hit or tp3_hit:
            PaperTradingService.close_trade(
                trade,
                price,
                "Stop loss or trailing stop" if stop_hit else "Take profit 3",
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
