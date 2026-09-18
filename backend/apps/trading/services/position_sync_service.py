from decimal import Decimal

from django.conf import settings

from ..models import BotLog, Trade, TradingBotConfig
from .discord_alert_service import send_discord_alert
from .live_trading_service import ExistingExchangePosition, LiveTradingDisabled, LiveTradingService
from .paper_trading_service import PaperTradingService
from .websocket_service import broadcast_user_update


def _log(config: TradingBotConfig, level: str, message: str) -> None:
    from ..serializers import BotLogSerializer

    log = BotLog.objects.create(user=config.user, symbol=config.symbol, level=level, message=message)
    broadcast_user_update(config.user_id, "log", BotLogSerializer(log).data)
    send_discord_alert(config.user, config.symbol, level, message)


def sync_master_close_to_followers(master_config: TradingBotConfig, master_trade: Trade) -> None:
    """Mirror the admin's just-closed trade to every regular user's matching
    open trade on the same symbol, so followers close at exactly the same
    time/price/reason as the admin instead of drifting apart on each
    follower's own trailing-stop/early-exit settings.
    """
    follower_trades = Trade.objects.filter(
        user__is_staff=False,
        symbol=master_config.symbol,
        status=Trade.Status.OPEN,
    ).select_related("user")

    for follower_trade in follower_trades:
        follower_config = TradingBotConfig.objects.filter(
            user=follower_trade.user, symbol=follower_trade.symbol
        ).first()
        if not follower_config:
            continue
        try:
            _close_follower_trade(follower_config, follower_trade, master_trade)
        except Exception as exc:
            _log(follower_config, BotLog.Level.ERROR, f"Position close sync from admin failed: {exc}")


def _close_follower_trade(
    follower_config: TradingBotConfig, follower_trade: Trade, master_trade: Trade
) -> None:
    if follower_trade.is_paper:
        PaperTradingService.close_trade(follower_trade, master_trade.exit_price, master_trade.close_reason)
    else:
        credential = getattr(follower_trade.user, "binance_credential", None)
        try:
            live_service = LiveTradingService(credential, follower_config)
        except LiveTradingDisabled as exc:
            _log(follower_config, BotLog.Level.WARNING, f"Position close sync skipped: {exc}")
            return
        existing_quantity = live_service.client.position_amount(follower_trade.symbol)
        if existing_quantity > 0:
            live_service.close_trade(follower_trade, master_trade.exit_price, master_trade.close_reason)
        else:
            # Already flat on the exchange (its own resting protective order
            # fired first) — just sync the DB record's close bookkeeping.
            PaperTradingService.close_trade(follower_trade, master_trade.exit_price, master_trade.close_reason)

    from ..serializers import TradeSerializer

    mode = "Paper" if follower_trade.is_paper else "Live"
    pnl = float(follower_trade.realized_pnl)
    roi = float(follower_trade.pnl_percent)
    _log(
        follower_config,
        BotLog.Level.INFO,
        f"{mode} {follower_trade.side} closed at {float(follower_trade.exit_price):.6f} "
        f"(synced from admin) — PnL {pnl:+.4f} USDT ({roi:+.2f}%). "
        f"Reason: {follower_trade.close_reason}",
    )
    broadcast_user_update(follower_trade.user_id, "position", TradeSerializer(follower_trade).data)


class _FollowerPlan:
    """Minimal stand-in for risk_service.RiskPlan — PaperTradingService.open_trade
    and LiveTradingService.place_entry only read these five attributes."""

    __slots__ = ("quantity", "stop_loss", "take_profit_1", "take_profit_2", "take_profit_3")

    def __init__(self, quantity, stop_loss, take_profit_1, take_profit_2, take_profit_3):
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.take_profit_1 = take_profit_1
        self.take_profit_2 = take_profit_2
        self.take_profit_3 = take_profit_3


def sync_master_trade_to_followers(
    master_config: TradingBotConfig,
    side: str,
    entry_price: float,
    master_plan,
    open_reason: str,
    setup_tags: list,
    replay_payload: dict,
) -> None:
    """Mirror a just-opened admin (master) trade to every regular user
    scanning the same symbol, at the same stop-loss/take-profit price
    levels, so every account ends up with the same position instead of
    each independently re-deciding entry off its own thresholds (which is
    what let one user open while another didn't).

    Only quantity varies, sized from each follower's own balance/margin/
    leverage — everything else about the position (symbol, side, SL, TP)
    is identical to the admin's.
    """
    # Deferred import: tasks.py imports this module at module load time,
    # so importing tasks back at module level here would be circular.
    from ..tasks import daily_loss_reached

    risk_per_unit = abs(entry_price - float(master_plan.stop_loss))
    if risk_per_unit <= 0:
        return

    followers = TradingBotConfig.objects.filter(
        user__is_staff=False,
        symbol=master_config.symbol,
        is_running=True,
    ).select_related("user")

    for follower_config in followers:
        if Trade.objects.filter(
            user=follower_config.user,
            symbol=follower_config.symbol,
            status=Trade.Status.OPEN,
        ).exists():
            continue

        open_count = Trade.objects.filter(
            user=follower_config.user, status=Trade.Status.OPEN
        ).count()
        if open_count >= follower_config.max_open_positions:
            _log(
                follower_config,
                BotLog.Level.INFO,
                f"Position sync skipped: maximum open positions reached "
                f"({open_count}/{follower_config.max_open_positions}).",
            )
            continue
        if daily_loss_reached(follower_config):
            _log(
                follower_config,
                BotLog.Level.WARNING,
                "Position sync skipped: daily loss limit reached.",
            )
            continue

        try:
            _open_follower_trade(
                follower_config,
                side,
                entry_price,
                master_plan,
                risk_per_unit,
                open_reason,
                setup_tags,
                replay_payload,
            )
        except Exception as exc:
            _log(follower_config, BotLog.Level.ERROR, f"Position sync from admin failed: {exc}")


def _open_follower_trade(
    follower_config: TradingBotConfig,
    side: str,
    entry_price: float,
    master_plan,
    risk_per_unit: float,
    open_reason: str,
    setup_tags: list,
    replay_payload: dict,
) -> None:
    use_live = bool(follower_config.live_mode_requested and settings.ENABLE_LIVE_TRADING)
    account_balance = float(follower_config.paper_balance)
    live_service = None
    if use_live:
        credential = getattr(follower_config.user, "binance_credential", None)
        try:
            live_service = LiveTradingService(credential, follower_config)
        except LiveTradingDisabled as exc:
            _log(follower_config, BotLog.Level.WARNING, f"Position sync skipped: {exc}")
            return
        existing_quantity = live_service.client.position_amount(follower_config.symbol)
        if existing_quantity > 0:
            _log(
                follower_config,
                BotLog.Level.INFO,
                f"Position sync skipped: {follower_config.symbol} already has an "
                f"open Binance position ({existing_quantity}).",
            )
            return
        account_balance = live_service.client.account_balance()

    effective_leverage = follower_config.leverage
    position_margin = (
        float(follower_config.position_margin_usdt)
        if follower_config.position_margin_usdt is not None
        else None
    )
    if position_margin is not None:
        if position_margin > account_balance:
            _log(
                follower_config,
                BotLog.Level.WARNING,
                f"Position sync skipped: position margin {position_margin:.2f} USDT "
                f"exceeds available balance {account_balance:.2f} USDT.",
            )
            return
        quantity = Decimal(str(position_margin * effective_leverage / entry_price))
    else:
        risk_amount = account_balance * float(follower_config.risk_per_trade_percent) / 100
        quantity = Decimal(str(risk_amount / risk_per_unit))

    if quantity <= 0:
        return

    plan = _FollowerPlan(
        quantity=quantity,
        stop_loss=master_plan.stop_loss,
        take_profit_1=master_plan.take_profit_1,
        take_profit_2=master_plan.take_profit_2,
        take_profit_3=master_plan.take_profit_3,
    )
    follower_reason = f"{open_reason} (synced from admin)"

    if live_service:
        try:
            order = live_service.place_entry(
                side,
                quantity,
                Decimal(str(entry_price)),
                Decimal(str(plan.stop_loss)),
                (
                    Decimal(str(plan.take_profit_1)),
                    Decimal(str(plan.take_profit_2)),
                    Decimal(str(plan.take_profit_3)),
                ),
                effective_leverage,
            )
        except ExistingExchangePosition as exc:
            _log(follower_config, BotLog.Level.INFO, f"Position sync skipped: {exc}")
            return
        executed_price = float(order.get("avgPrice") or entry_price)
        executed_quantity = Decimal(str(order.get("executedQty") or quantity))
        trade = Trade.objects.create(
            user=follower_config.user,
            symbol=follower_config.symbol,
            side=side,
            entry_price=executed_price,
            quantity=executed_quantity,
            remaining_quantity=executed_quantity,
            leverage=effective_leverage,
            stop_loss=plan.stop_loss,
            initial_stop_loss=plan.stop_loss,
            take_profit_1=plan.take_profit_1,
            take_profit_2=plan.take_profit_2,
            take_profit_3=plan.take_profit_3,
            open_reason=follower_reason,
            setup_tags=setup_tags,
            replay_payload=replay_payload,
            is_paper=False,
            partial_entry_filled=True,
        )
    else:
        trade = PaperTradingService.open_trade(
            follower_config.user,
            follower_config,
            side,
            entry_price,
            plan,
            follower_reason,
            setup_tags,
            effective_leverage,
            replay_payload,
        )

    from ..serializers import TradeSerializer

    _log(
        follower_config,
        BotLog.Level.INFO,
        f"{'Live' if live_service else 'Paper'} {side} opened at {entry_price:.6f} "
        f"(synced from admin), x{effective_leverage}.",
    )
    broadcast_user_update(follower_config.user_id, "position", TradeSerializer(trade).data)
