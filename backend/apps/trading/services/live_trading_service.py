from django.conf import settings
from decimal import Decimal, ROUND_DOWN
from django.utils import timezone
import time

from .binance_service import BinanceService
from .credential_service import decrypt_secret
from .paper_trading_service import PaperTradingService
from apps.trading.models import Trade


class LiveTradingDisabled(RuntimeError):
    pass


class ExistingExchangePosition(RuntimeError):
    pass


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
        normalized_stop = (
            Decimal(str(stop_loss)) / tick
        ).to_integral_value(rounding=ROUND_DOWN) * tick
        normalized_take_profits = tuple(
            (Decimal(str(target)) / tick).to_integral_value(rounding=ROUND_DOWN) * tick
            for target in take_profits
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
        take_profit_orders = tuple(
            self.client.place_close_algo_order(
                self.config.symbol,
                close_side,
                "TAKE_PROFIT_MARKET",
                target,
                f"bot-tp{index}-{nonce}",
                quantity=target_quantity,
            )
            for index, (target, target_quantity) in enumerate(
                zip(
                    normalized_take_profits,
                    (tp1_quantity, tp2_quantity, tp3_quantity),
                ),
                start=1,
            )
        )
        return (stop_order, *take_profit_orders)

    def close_position(self, position_side: str, quantity, price) -> dict:
        rules = self.client.symbol_rules(self.config.symbol)
        _, normalized_quantity = self.client.normalize_order(price, quantity, rules)
        exchange_side = "SELL" if position_side == "LONG" else "BUY"
        return self.client.place_market_order(
            self.config.symbol,
            exchange_side,
            normalized_quantity,
            reduce_only=True,
        )

    def update_trade(self, trade: Trade, current_price: float, atr: float, trailing_multiplier: float) -> Trade:
        price = Decimal(str(current_price))
        exchange_quantity = self.client.position_amount(self.config.symbol)
        if exchange_quantity <= 0:
            self.client.cancel_all_algo_orders(self.config.symbol)
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
            trade.remaining_quantity = exchange_quantity
            trade.tp1_hit = exchange_quantity <= trade.quantity * Decimal("0.70")
            trade.tp2_hit = exchange_quantity <= trade.quantity * Decimal("0.30")
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
