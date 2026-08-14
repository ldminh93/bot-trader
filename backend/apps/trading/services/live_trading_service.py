from django.conf import settings
from decimal import Decimal, ROUND_DOWN
from django.utils import timezone
import time

from .binance_service import BinanceService
from .credential_service import decrypt_secret
from .paper_trading_service import TAKER_FEE_RATE, PaperTradingService, _apply_profit_steps
from apps.trading.models import Trade


class LiveTradingDisabled(RuntimeError):
    pass


class ExistingExchangePosition(RuntimeError):
    pass


def _safe_stop_price(side: str, stop_price: Decimal, mark_price: Decimal, tick: Decimal, buffer_ticks: int = 2) -> Decimal:
    """Keep a STOP_MARKET trigger on the side of mark price that won't fire immediately."""
    buffer = tick * buffer_ticks
    if side == "LONG":
        return min(stop_price, mark_price - buffer)
    return max(stop_price, mark_price + buffer)


def _safe_take_profit_price(side: str, target_price: Decimal, mark_price: Decimal, tick: Decimal, buffer_ticks: int = 2) -> Decimal:
    """Keep a TAKE_PROFIT_MARKET trigger on the side of mark price that won't fire immediately."""
    buffer = tick * buffer_ticks
    if side == "LONG":
        return max(target_price, mark_price + buffer)
    return min(target_price, mark_price - buffer)


class LiveTradingService:
    def __init__(self, credential, config) -> None:
        if not settings.ENABLE_LIVE_TRADING:
            raise LiveTradingDisabled("ENABLE_LIVE_TRADING is false")
        if not config.live_mode_requested:
            raise LiveTradingDisabled("Live mode was not explicitly enabled by the user")
        if not credential or not credential.is_active:
            raise LiveTradingDisabled("Active Binance credentials are required")
        self.credential = credential
        self.config = config
        self.client = BinanceService(
            api_key=credential.api_key,
            api_secret=decrypt_secret(credential.api_secret_encrypted),
        )

    def place_entry(
        self,
        side: str,
        quantity,
        price,
        stop_loss: Decimal,
        take_profit: tuple[Decimal, Decimal, Decimal],
        leverage: int | None = None,
    ) -> dict:
        existing_quantity = self.client.position_amount(self.config.symbol)
        if existing_quantity > 0:
            raise ExistingExchangePosition(
                f"{self.config.symbol} already has an open Binance position "
                f"({existing_quantity}); additional entry skipped"
            )
        rules = self.client.symbol_rules(self.config.symbol)
        normalized_price, normalized_quantity = self.client.normalize_order(price, quantity, rules)
        self.client.set_margin_type(self.config.symbol, self.config.margin_type)
        self.client.set_leverage(self.config.symbol, leverage or self.config.leverage)
        exchange_side = "BUY" if side == "LONG" else "SELL"
        order = self.client.place_market_order(
            self.config.symbol,
            exchange_side,
            normalized_quantity,
            reduce_only=False,
        )
        try:
            self.place_protective_orders(
                side,
                stop_loss,
                take_profit,
                normalized_quantity,
                rules.tick_size,
                rules.step_size,
            )
        except Exception:
            try:
                self.client.cancel_all_algo_orders(self.config.symbol)
            finally:
                executed_quantity = Decimal(str(order.get("executedQty") or normalized_quantity))
                executed_price = Decimal(str(order.get("avgPrice") or normalized_price))
                self.close_position(side, executed_quantity, executed_price)
            raise
        return order

    def place_protective_orders(
        self,
        side: str,
        stop_loss: Decimal,
        take_profits: tuple[Decimal, Decimal, Decimal],
        quantity: Decimal,
        tick_size: Decimal | None = None,
        step_size: Decimal | None = None,
    ) -> tuple[dict, dict, dict, dict]:
        rules = (
            self.client.symbol_rules(self.config.symbol)
            if tick_size is None or step_size is None
            else None
        )
        tick = tick_size or rules.tick_size
        step = step_size or rules.step_size
        mark_price = self.client.mark_price(self.config.symbol)
        normalized_stop = (
            Decimal(str(stop_loss)) / tick
        ).to_integral_value(rounding=ROUND_DOWN) * tick
        normalized_stop = (
            _safe_stop_price(side, normalized_stop, mark_price, tick) / tick
        ).to_integral_value(rounding=ROUND_DOWN) * tick
        normalized_take_profits = tuple(
            (Decimal(str(target)) / tick).to_integral_value(rounding=ROUND_DOWN) * tick
            for target in take_profits
        )
        normalized_take_profits = tuple(
            (_safe_take_profit_price(side, target, mark_price, tick) / tick).to_integral_value(
                rounding=ROUND_DOWN
            )
            * tick
            for target in normalized_take_profits
        )
        tp1_quantity = (
            quantity * Decimal("0.30") / step
        ).to_integral_value(rounding=ROUND_DOWN) * step
        tp2_quantity = (
            quantity * Decimal("0.40") / step
        ).to_integral_value(rounding=ROUND_DOWN) * step
        tp3_quantity = quantity - tp1_quantity - tp2_quantity
        close_side = "SELL" if side == "LONG" else "BUY"
        nonce = int(time.time() * 1000)
        stop_order = self.client.place_close_algo_order(
            self.config.symbol,
            close_side,
            "STOP_MARKET",
            normalized_stop,
            f"bot-sl-{nonce}",
            close_position=True,
        )
        tp3_trailing = float(getattr(self.config, "tp3_trailing_percent", 0) or 0)
        tp_targets = (
            list(zip(normalized_take_profits[:2], (tp1_quantity, tp2_quantity)))
            if tp3_trailing > 0
            else list(zip(normalized_take_profits, (tp1_quantity, tp2_quantity, tp3_quantity)))
        )
        take_profit_orders = tuple(
            self.client.place_close_algo_order(
                self.config.symbol,
                close_side,
                "TAKE_PROFIT_MARKET",
                target,
                f"bot-tp{index}-{nonce}",
                quantity=target_quantity,
            )
            # A leg quantity can floor to 0 at the symbol's LOT_SIZE step for
            # small positions; submitting a 0-quantity order gets rejected by
            # Binance, which used to bubble up and trip place_entry's
            # emergency full-close right after every such entry.
            for index, (target, target_quantity) in enumerate(tp_targets, start=1)
            if target_quantity > 0
        )
        # TP3 is the "runner" leg: rather than a fixed TAKE_PROFIT_MARKET,
        # place a real exchange-side trailing stop so it's visible on Binance
        # and still executes if the bot process is down. It only starts
        # trailing once price reaches take_profit_3 (activationPrice), which
        # is beyond TP1/TP2's targets, so it won't fire before those legs
        # have already been taken. TRAILING_STOP_MARKET rejects
        # closePosition=true outright (Binance error -4136 "Target strategy
        # invalid for orderType TRAILING_STOP_MARKET,closePosition true") —
        # it only accepts an explicit quantity, same as TP1/TP2.
        trailing_order = None
        if tp3_trailing > 0 and tp3_quantity > 0:
            trailing_order = self.client.place_close_algo_order(
                self.config.symbol,
                close_side,
                "TRAILING_STOP_MARKET",
                normalized_take_profits[2],
                f"bot-tp3trail-{nonce}",
                quantity=tp3_quantity,
                callback_rate=Decimal(str(tp3_trailing)).quantize(Decimal("0.1")),
            )
        orders = (stop_order, *take_profit_orders)
        return orders + (trailing_order,) if trailing_order else orders

    def close_position(self, position_side: str, quantity, price) -> dict | None:
        rules = self.client.symbol_rules(self.config.symbol)
        # skip_min_notional: this unwinds an existing position rather than opening
        # new exposure (e.g. the small runner leftover after TP1/TP2 fills), so the
        # MIN_NOTIONAL floor that guards new entries must not block it here.
        _, normalized_quantity = self.client.normalize_order(
            price, quantity, rules, skip_min_notional=True
        )
        if normalized_quantity <= 0:
            return None
        exchange_side = "SELL" if position_side == "LONG" else "BUY"
        return self.client.place_market_order(
            self.config.symbol,
            exchange_side,
            normalized_quantity,
            reduce_only=True,
        )

    def update_trade(self, trade: Trade, current_price: float, atr: float, trailing_multiplier: float, tp3_trailing_percent: float = 0) -> Trade:
        price = Decimal(str(current_price))
        exchange_quantity = self.client.position_amount(self.config.symbol)
        if exchange_quantity <= 0:
            self.client.cancel_all_algo_orders(self.config.symbol)
            # TP1/TP2 are inferred from quantity fraction below; a full close
            # after TP2 already fired means the TP3 trailing leg is what closed
            # the runner, so mirror that bookkeeping for admin/analytics.
            if trade.tp2_hit:
                trade.tp3_hit = True
            avg_exit_price, gross_pnl, total_commission = self._sync_close_from_fills(trade)
            closed = PaperTradingService.close_trade(
                trade,
                avg_exit_price if avg_exit_price is not None else price,
                "Live position closed by exchange protective order",
            )
            if gross_pnl is not None:
                closed.realized_pnl = gross_pnl - total_commission
                closed.fees = total_commission
                margin_basis = PaperTradingService._margin_basis(closed)
                closed.pnl_percent = (
                    closed.realized_pnl / margin_basis * 100 if margin_basis else Decimal("0")
                )
                closed.save(update_fields=["realized_pnl", "fees", "pnl_percent"])
            return closed
        if exchange_quantity < trade.remaining_quantity:
            closed_quantity = trade.remaining_quantity - exchange_quantity
            was_tp1_hit, was_tp2_hit = trade.tp1_hit, trade.tp2_hit
            trade.remaining_quantity = exchange_quantity
            trade.tp1_hit = exchange_quantity <= trade.quantity * Decimal("0.70")
            trade.tp2_hit = exchange_quantity <= trade.quantity * Decimal("0.30")
            # Binance's own TP algo order is the ground truth for this leg's
            # exact fill price/PnL — _sync_close_from_fills applies the precise
            # figure once the position is fully closed (see below). But that
            # lookup can fail (API error, rate limit, no matching fills), and
            # when it does, close_trade()'s own _partial_close(fraction=1) only
            # covers whatever quantity remains at that point — silently losing
            # every earlier TP leg's profit from the trade's total. Accrue a
            # same-formula estimate now, using the leg's own target price, so
            # realized_pnl is never simply missing a leg if that fallback fires.
            if closed_quantity > 0:
                estimate_price = (
                    trade.take_profit_2 if (trade.tp2_hit and not was_tp2_hit)
                    else trade.take_profit_1 if (trade.tp1_hit and not was_tp1_hit)
                    else price
                )
                direction = Decimal("1") if trade.side == Trade.Side.LONG else Decimal("-1")
                gross = (estimate_price - trade.entry_price) * closed_quantity * direction
                fee = estimate_price * closed_quantity * TAKER_FEE_RATE
                trade.realized_pnl += gross - fee
                trade.fees += fee

        # TP3 trailing is now a real TRAILING_STOP_MARKET order resting on
        # Binance (see place_protective_orders/_update_exchange_sl) rather
        # than software-polled — its fill is picked up generically by the
        # exchange_quantity <= 0 branch above, so no local tracking here.

        # Stepped profit-protection SL — update exchange SL if it moved
        early_be = float(getattr(self.config, "early_breakeven_r", 0) or 0)
        lock_pr = float(getattr(self.config, "lock_profit_r", 0) or 0)
        sl_changed = _apply_profit_steps(trade, price, atr, trailing_multiplier, early_be, lock_pr)
        if sl_changed:
            self._update_exchange_sl(trade, tp3_trailing_percent)

        try:
            trade.unrealized_pnl = self.client.position_unrealized_pnl(self.config.symbol)
        except Exception:
            direction = Decimal("1") if trade.side == Trade.Side.LONG else Decimal("-1")
            trade.unrealized_pnl = (price - trade.entry_price) * trade.remaining_quantity * direction
        margin_basis = PaperTradingService._margin_basis(trade)
        trade.pnl_percent = (
            (trade.realized_pnl + trade.unrealized_pnl) / margin_basis * 100
            if margin_basis
            else Decimal("0")
        )
        trade.save()
        return trade

    def _update_exchange_sl(self, trade: Trade, tp3_trailing_percent: float = 0) -> None:
        """Cancel all protective orders and re-place with the updated stop loss."""
        rules = self.client.symbol_rules(self.config.symbol)
        tick = rules.tick_size
        step = rules.step_size
        close_side = "SELL" if trade.side == Trade.Side.LONG else "BUY"
        nonce = int(time.time() * 1000)
        mark_price = self.client.mark_price(self.config.symbol)
        normalized_sl = (trade.stop_loss / tick).to_integral_value(rounding=ROUND_DOWN) * tick
        normalized_sl = (
            _safe_stop_price(trade.side, normalized_sl, mark_price, tick) / tick
        ).to_integral_value(rounding=ROUND_DOWN) * tick

        self.client.cancel_all_algo_orders(self.config.symbol)

        self.client.place_close_algo_order(
            self.config.symbol,
            close_side,
            "STOP_MARKET",
            normalized_sl,
            f"bot-sl-{nonce}",
            close_position=True,
        )

        # Re-place TP orders that haven't fired yet
        original_qty = trade.quantity
        tp1_qty = (original_qty * Decimal("0.30") / step).to_integral_value(rounding=ROUND_DOWN) * step
        tp2_qty = (original_qty * Decimal("0.40") / step).to_integral_value(rounding=ROUND_DOWN) * step
        tp3_qty = original_qty - tp1_qty - tp2_qty
        remaining_tps = []
        if not trade.tp1_hit:
            remaining_tps.append((trade.take_profit_1, tp1_qty, "tp1"))
        if not trade.tp2_hit:
            remaining_tps.append((trade.take_profit_2, tp2_qty, "tp2"))
        if not trade.tp3_hit and tp3_trailing_percent == 0:
            remaining_tps.append((trade.take_profit_3, tp3_qty, "tp3"))
        for tp_price, tp_qty, label in remaining_tps:
            normalized_tp = (tp_price / tick).to_integral_value(rounding=ROUND_DOWN) * tick
            normalized_tp = (
                _safe_take_profit_price(trade.side, normalized_tp, mark_price, tick) / tick
            ).to_integral_value(rounding=ROUND_DOWN) * tick
            normalized_qty = (tp_qty / step).to_integral_value(rounding=ROUND_DOWN) * step
            if normalized_qty > 0:
                self.client.place_close_algo_order(
                    self.config.symbol,
                    close_side,
                    "TAKE_PROFIT_MARKET",
                    normalized_tp,
                    f"bot-{label}-{nonce}",
                    quantity=normalized_qty,
                )
        if not trade.tp3_hit and tp3_trailing_percent > 0:
            normalized_tp3 = (trade.take_profit_3 / tick).to_integral_value(rounding=ROUND_DOWN) * tick
            normalized_tp3 = (
                _safe_take_profit_price(trade.side, normalized_tp3, mark_price, tick) / tick
            ).to_integral_value(rounding=ROUND_DOWN) * tick
            # TRAILING_STOP_MARKET rejects closePosition=true (Binance error
            # -4136) — needs an explicit quantity, same as TP1/TP2 above.
            normalized_tp3_qty = (tp3_qty / step).to_integral_value(rounding=ROUND_DOWN) * step
            if normalized_tp3_qty > 0:
                self.client.place_close_algo_order(
                    self.config.symbol,
                    close_side,
                    "TRAILING_STOP_MARKET",
                    normalized_tp3,
                    f"bot-tp3trail-{nonce}",
                    quantity=normalized_tp3_qty,
                    callback_rate=Decimal(str(tp3_trailing_percent)).quantize(Decimal("0.1")),
                )

    def _sync_close_from_fills(
        self, trade: Trade
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
        """
        Fetches actual fills from Binance since the trade opened.
        Returns (avg_exit_price, gross_realized_pnl, total_commission).
        Falls back to (None, None, None) on any error.
        Binance reports realizedPnl=0 on entry fills and the actual value on closing fills,
        so summing all realizedPnl gives the correct gross PnL for the position.
        """
        try:
            opened_at_ms = int(trade.opened_at.timestamp() * 1000)
            fills = self.client.user_trades(self.config.symbol, opened_at_ms)
            if not fills:
                return None, None, None
            close_side = "SELL" if trade.side == Trade.Side.LONG else "BUY"
            exit_fills = [
                f for f in fills
                if f.get("side") == close_side and Decimal(str(f.get("realizedPnl", "0"))) != 0
            ]
            if not exit_fills:
                return None, None, None
            total_exit_qty = sum(Decimal(str(f["qty"])) for f in exit_fills)
            total_exit_value = sum(Decimal(str(f["price"])) * Decimal(str(f["qty"])) for f in exit_fills)
            avg_exit_price = total_exit_value / total_exit_qty if total_exit_qty else None
            gross_pnl = sum(Decimal(str(f["realizedPnl"])) for f in exit_fills)
            # Sum commissions from all fills (entry + exit) to get the total cost of the trade
            total_commission = sum(Decimal(str(f.get("commission", "0"))) for f in fills)
            return avg_exit_price, gross_pnl, total_commission
        except Exception:
            return None, None, None

    def close_trade(self, trade: Trade, price: Decimal, reason: str) -> Trade:
        self.close_position(trade.side, trade.remaining_quantity, price)
        self.client.cancel_all_algo_orders(self.config.symbol)
        return PaperTradingService.close_trade(trade, price, reason)

    def _reduce(self, trade: Trade, price: Decimal, fraction: Decimal) -> None:
        quantity = min(trade.remaining_quantity, trade.quantity * fraction)
        if quantity <= 0:
            return
        self.close_position(trade.side, quantity, price)
        PaperTradingService._partial_close(trade, price, fraction)
