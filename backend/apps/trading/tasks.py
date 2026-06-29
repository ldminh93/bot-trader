import logging
import uuid
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from redis import Redis

from .models import BotLog, MarketSnapshot, Trade, TradingBotConfig
from .serializers import BotLogSerializer, MarketSnapshotSerializer, TradeSerializer
from .services.paper_trading_service import PaperTradingService
from .services.live_trading_service import ExistingExchangePosition, LiveTradingService
from .services.early_exit_service import (
    evaluate_early_exit,
    opposite_entry_has_new_candle_confirmation,
)
from .services.market_snapshot_service import collect_market_snapshot
from .services.risk_service import RiskLimitExceeded, calculate_risk_plan
from .services.signal_service import entry_location_block_reason
from .services.websocket_service import broadcast_user_update
from .services.discord_alert_service import send_discord_alert

logger = logging.getLogger(__name__)
redis_client = Redis.from_url(settings.REDIS_URL)

def create_log(config: TradingBotConfig, level: str, message: str) -> BotLog:
    log = BotLog.objects.create(
        user=config.user,
        symbol=config.symbol,
        level=level,
        message=message,
    )
    broadcast_user_update(config.user_id, "log", BotLogSerializer(log).data)
    send_discord_alert(config.user, config.symbol, level, message)
    return log


def _suppressed_tags(config: TradingBotConfig, setup_tags: list[str]) -> list[str]:
    """Return tags whose last 20+ closed trades have a win rate below 40%."""
    MIN_TRADES = 20
    MIN_WIN_RATE = 0.40
    suppressed = []
    for tag in setup_tags:
        pnl_values = list(
            Trade.objects.filter(
                user=config.user,
                setup_tags__contains=[tag],
                status=Trade.Status.CLOSED,
            )
            .order_by("-opened_at")
            .values_list("realized_pnl", flat=True)[:MIN_TRADES]
        )
        if len(pnl_values) >= MIN_TRADES:
            wins = sum(1 for pnl in pnl_values if float(pnl) > 0)
            if wins / len(pnl_values) < MIN_WIN_RATE:
                suppressed.append(tag)
    return suppressed


def daily_loss_reached(config: TradingBotConfig) -> bool:
    today = timezone.now().date()
    realized = (
        Trade.objects.filter(
            user=config.user,
            closed_at__date=today,
            status=Trade.Status.CLOSED,
        ).aggregate(total=Sum("realized_pnl"))["total"]
        or Decimal("0")
    )
    limit = config.paper_balance * config.max_daily_loss_percent / Decimal("100")
    return realized <= -limit


def process_config(config: TradingBotConfig) -> None:
    evaluation = collect_market_snapshot(config)
    snapshot = evaluation.snapshot
    signal_indicators = evaluation.indicators
    metrics = evaluation.metrics
    signal = evaluation.signal
    broadcast_user_update(config.user_id, "snapshot", MarketSnapshotSerializer(snapshot).data)

    open_trade = Trade.objects.filter(
        user=config.user,
        symbol=config.symbol,
        status=Trade.Status.OPEN,
    ).first()
    if open_trade:
        if open_trade.is_paper:
            PaperTradingService.update_trade(
                open_trade,
                metrics["price"],
                signal_indicators.atr,
                float(config.trailing_atr_multiplier) if config.use_trailing_stop else 0,
            )
        else:
            credential = getattr(config.user, "binance_credential", None)
            LiveTradingService(credential, config).update_trade(
                open_trade,
                metrics["price"],
                signal_indicators.atr,
                float(config.trailing_atr_multiplier) if config.use_trailing_stop else 0,
            )
        if open_trade.status == Trade.Status.CLOSED:
            mode = "Paper" if open_trade.is_paper else "Live"
            pnl = float(open_trade.realized_pnl)
            roi = float(open_trade.pnl_percent)
            create_log(
                config,
                BotLog.Level.INFO,
                f"{mode} {open_trade.side} closed at {float(open_trade.exit_price):.6f} — "
                f"PnL {pnl:+.4f} USDT ({roi:+.2f}%). "
                f"Reason: {open_trade.close_reason}",
            )
            broadcast_user_update(config.user_id, "position", TradeSerializer(open_trade).data)
            return
        if open_trade.status == Trade.Status.OPEN:
            early_exit = evaluate_early_exit(
                open_trade,
                config,
                signal.long_score,
                signal.short_score,
            )
            if early_exit.should_close:
                close_price = Decimal(str(metrics["price"]))
                if open_trade.is_paper:
                    PaperTradingService.close_trade(
                        open_trade,
                        close_price,
                        early_exit.reason,
                    )
                else:
                    credential = getattr(config.user, "binance_credential", None)
                    LiveTradingService(credential, config).close_trade(
                        open_trade,
                        close_price,
                        early_exit.reason,
                    )
                create_log(
                    config,
                    BotLog.Level.WARNING,
                    early_exit.reason,
                )
        broadcast_user_update(config.user_id, "position", TradeSerializer(open_trade).data)
        return

    if signal.signal == "NO_TRADE":
        return
    if not opposite_entry_has_new_candle_confirmation(
        config.user,
        config.symbol,
        signal.signal,
        signal_indicators.candles,
    ):
        create_log(
            config,
            BotLog.Level.INFO,
            "Opposite entry blocked until one newly closed signal candle confirms.",
        )
        return
    if daily_loss_reached(config):
        create_log(config, BotLog.Level.WARNING, "Daily loss limit reached. New entries are blocked.")
        return
    open_count = Trade.objects.filter(user=config.user, status=Trade.Status.OPEN).count()
    if open_count >= config.max_open_positions:
        create_log(
            config,
            BotLog.Level.INFO,
            f"Maximum open positions reached ({open_count}/{config.max_open_positions}).",
        )
        return

    price = metrics["price"]

    # ATR minimum-percent filter
    if float(config.atr_min_percent) > 0 and price > 0:
        atr_pct = signal_indicators.atr / price * 100
        if atr_pct < float(config.atr_min_percent):
            create_log(
                config,
                BotLog.Level.INFO,
                f"Entry skipped: ATR ({atr_pct:.3f}% of price) is below the "
                f"{float(config.atr_min_percent):.2f}% minimum — market is too quiet.",
            )
            return

    # Auto-suppress setup tags with poor historical win rate
    if config.auto_suppress_losing_tags:
        snapshot_tags = snapshot.payload.get("setup_tags", [])
        bad_tags = _suppressed_tags(config, snapshot_tags)
        if bad_tags:
            create_log(
                config,
                BotLog.Level.INFO,
                f"Entry skipped: setup tag(s) {', '.join(bad_tags)} have <40% win rate "
                f"over the last 20 trades.",
            )
            return

    execution_payload = snapshot.payload
    effective_leverage = int(execution_payload.get("effective_leverage") or config.leverage)
    tp_r_multiple = float(execution_payload.get("tp_r_multiple") or config.atr_multiplier_tp)
    location_reason = None
    if config.pullback_entry_enabled:
        location_reason = entry_location_block_reason(
            signal.signal,
            price,
            signal_indicators.ma7,
            signal_indicators.ma25,
            signal_indicators.atr,
            float(config.max_entry_distance_atr),
        )
    if location_reason:
        create_log(config, BotLog.Level.INFO, f"Entry skipped: {location_reason}")
        return

    use_live = bool(config.live_mode_requested and settings.ENABLE_LIVE_TRADING)
    account_balance = float(config.paper_balance)
    live_service = None
    if use_live:
        credential = getattr(config.user, "binance_credential", None)
        live_service = LiveTradingService(credential, config)
        existing_quantity = live_service.client.position_amount(config.symbol)
        if existing_quantity > 0:
            create_log(
                config,
                BotLog.Level.INFO,
                f"Entry skipped: {config.symbol} already has an open Binance "
                f"position ({existing_quantity}).",
            )
            return
        account_balance = live_service.client.account_balance()
    position_margin = (
        float(config.position_margin_usdt) * signal.risk_multiplier
        if config.position_margin_usdt is not None
        else None
    )
    if position_margin is not None and position_margin > account_balance:
        create_log(
            config,
            BotLog.Level.WARNING,
            f"Position margin {position_margin:.2f} USDT exceeds available balance "
            f"{account_balance:.2f} USDT.",
        )
        return

    try:
        plan = calculate_risk_plan(
            signal.signal,
            price,
            account_balance,
            float(config.risk_per_trade_percent) * signal.risk_multiplier,
            signal_indicators.atr,
            signal_indicators.swing_high,
            signal_indicators.swing_low,
            signal_indicators.ma7,
            signal_indicators.ma25,
            signal_indicators.ma99,
            position_margin,
            effective_leverage,
            float(config.atr_multiplier_sl),
            tp_r_multiple,
            float(config.max_margin_loss_percent),
        )
    except RiskLimitExceeded as exc:
        create_log(config, BotLog.Level.INFO, f"Entry skipped: {exc}")
        return
    replay_payload = {
        "entry_timeframe": config.timeframe_signal,
        "trend_timeframe": config.timeframe_trend,
        "candles": snapshot.payload.get("candles", []),
        "signal": snapshot.payload.get("signal", signal.signal),
        "trend_state": snapshot.payload.get("trend_state"),
        "higher_timeframe_bias": snapshot.payload.get("higher_timeframe_bias", {}),
        "reasons": snapshot.payload.get("reasons", signal.reasons),
        "trend_reasons": snapshot.payload.get("trend_reasons", []),
        "regime": snapshot.payload.get("regime"),
        "regime_label": snapshot.payload.get("regime_label"),
        "regime_notes": snapshot.payload.get("regime_notes", []),
        "confidence_score": snapshot.payload.get("confidence_score", 0),
        "trade_grade": snapshot.payload.get("trade_grade", "D"),
        "opportunity_score": snapshot.payload.get("opportunity_score", 0),
        "effective_leverage": effective_leverage,
        "tp_r_multiple": tp_r_multiple,
        "metrics": {
            "price": metrics["price"],
            "adx": signal_indicators.adx,
            "atr": signal_indicators.atr,
            "volume": signal_indicators.volume,
            "volume_ma20": signal_indicators.volume_ma20,
            "open_interest": metrics["open_interest"],
            "open_interest_change_percent": metrics["open_interest_change_percent"],
            "funding_rate": metrics["funding_rate"],
        },
    }
    trade_setup_tags = list(
        dict.fromkeys(
            [
                *snapshot.payload.get("setup_tags", []),
                f"regime:{str(snapshot.payload.get('regime', 'manual')).lower()}",
                f"confidence:{snapshot.payload.get('confidence_score', 0)}",
                f"grade:{snapshot.payload.get('trade_grade', 'D')}",
            ]
        )
    )
    if live_service:
        try:
            order = live_service.place_entry(
                signal.signal,
                plan.quantity,
                Decimal(str(price)),
                plan.stop_loss,
                (
                    plan.take_profit_1,
                    plan.take_profit_2,
                    plan.take_profit_3,
                ),
                effective_leverage,
            )
        except ExistingExchangePosition as exc:
            create_log(config, BotLog.Level.INFO, f"Entry skipped: {exc}")
            return
        executed_price = float(order.get("avgPrice") or price)
        executed_quantity = Decimal(str(order.get("executedQty") or plan.quantity))
        trade = Trade.objects.create(
            user=config.user,
            symbol=config.symbol,
            side=signal.signal,
            entry_price=executed_price,
            quantity=executed_quantity,
            remaining_quantity=executed_quantity,
            leverage=effective_leverage,
            stop_loss=plan.stop_loss,
            take_profit_1=plan.take_profit_1,
            take_profit_2=plan.take_profit_2,
            take_profit_3=plan.take_profit_3,
            open_reason=", ".join(signal.reasons),
            setup_tags=trade_setup_tags,
            replay_payload=replay_payload,
            is_paper=False,
        )
    else:
        trade = PaperTradingService.open_trade(
            config.user,
            config,
            signal.signal,
            price,
            plan,
            ", ".join(signal.reasons),
            trade_setup_tags,
            effective_leverage,
            replay_payload,
        )
    sizing_message = (
        f"{position_margin:.2f} USDT margin "
        f"({plan.risk_amount:.2f} USDT at stop)"
        if position_margin is not None
        else f"{signal.risk_multiplier:.0%} risk ({plan.risk_amount:.2f} USDT)"
    )
    create_log(
        config,
        BotLog.Level.INFO,
        f"{'Live' if use_live else 'Paper'} {signal.signal} opened at {price:.6f} "
        f"with {sizing_message}, x{effective_leverage}, {snapshot.payload.get('regime_label', 'Manual')} regime, "
        f"TP {tp_r_multiple:.2f}R, grade {snapshot.payload.get('trade_grade', 'D')}, "
        f"confidence {snapshot.payload.get('confidence_score', 0)}.",
    )
    broadcast_user_update(config.user_id, "position", TradeSerializer(trade).data)


@shared_task
def run_active_bots() -> None:
    for config in TradingBotConfig.objects.filter(is_running=True).select_related("user"):
        lock_key = f"trading:cycle:{config.pk}"
        lock_token = uuid.uuid4().hex
        if not redis_client.set(lock_key, lock_token, nx=True, ex=60):
            continue
        try:
            process_config(config)
        except Exception as exc:
            logger.exception("Bot cycle failed for config %s", config.pk)
            create_log(config, BotLog.Level.ERROR, f"Bot cycle failed: {exc}")
        finally:
            redis_client.eval(
                """
                if redis.call("get", KEYS[1]) == ARGV[1] then
                    return redis.call("del", KEYS[1])
                end
                return 0
                """,
                1,
                lock_key,
                lock_token,
            )
