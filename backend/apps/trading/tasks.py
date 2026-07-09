import logging
import uuid
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from redis import Redis

from .models import AutoScannerSettings, BotLog, MarketSnapshot, Trade, TradingBotConfig
from .serializers import BotLogSerializer, MarketSnapshotSerializer, TradeSerializer
from .services.auto_scanner_service import sync_top_movers_to_scanner
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


def _timeframe_minutes(tf: str) -> int:
    return {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "1d": 1440}.get(tf, 15)


def _consecutive_losses(config: TradingBotConfig) -> int:
    """Count the most-recent consecutive losing trades for this symbol."""
    recent = list(
        Trade.objects.filter(
            user=config.user,
            symbol=config.symbol,
            status=Trade.Status.CLOSED,
        )
        .order_by("-closed_at")
        .values_list("realized_pnl", flat=True)[:10]
    )
    count = 0
    for pnl in recent:
        if float(pnl) < 0:
            count += 1
        else:
            break
    return count


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


def _is_symbol_losing(config: TradingBotConfig) -> bool:
    """True when this symbol's last 20+ closed trades have a win rate below 40%."""
    MIN_TRADES = 20
    MIN_WIN_RATE = 0.40
    pnl_values = list(
        Trade.objects.filter(
            user=config.user,
            symbol=config.symbol,
            status=Trade.Status.CLOSED,
        )
        .order_by("-opened_at")
        .values_list("realized_pnl", flat=True)[:MIN_TRADES]
    )
    if len(pnl_values) < MIN_TRADES:
        return False
    wins = sum(1 for pnl in pnl_values if float(pnl) > 0)
    return wins / len(pnl_values) < MIN_WIN_RATE


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
        # Partial entry scale-in: add remaining quantity when price confirms above/below MA7
        if config.partial_entry_enabled and not open_trade.partial_entry_filled:
            price_f = float(metrics["price"])
            ma7_f = float(signal_indicators.ma7)
            pct = Decimal(str(config.partial_entry_size_pct))
            remaining_qty = open_trade.quantity * (Decimal("100") - pct) / pct
            confirmed = (
                (open_trade.side == Trade.Side.LONG and price_f > ma7_f) or
                (open_trade.side == Trade.Side.SHORT and price_f < ma7_f)
            )
            if confirmed and remaining_qty > Decimal("0"):
                if open_trade.is_paper:
                    PaperTradingService.scale_in_entry(open_trade, price_f, remaining_qty)
                else:
                    credential = getattr(config.user, "binance_credential", None)
                    live_svc = LiveTradingService(credential, config)
                    try:
                        rules = live_svc.client.symbol_rules(config.symbol)
                        _, norm_qty = live_svc.client.normalize_order(
                            Decimal(str(price_f)), remaining_qty, rules
                        )
                        exchange_side = "BUY" if open_trade.side == Trade.Side.LONG else "SELL"
                        live_svc.client.place_market_order(
                            config.symbol, exchange_side, norm_qty, reduce_only=False
                        )
                        open_trade.quantity += remaining_qty
                        open_trade.remaining_quantity += remaining_qty
                        open_trade.partial_entry_filled = True
                        open_trade.save()
                        live_svc._update_exchange_sl(
                            open_trade, float(config.tp3_trailing_percent)
                        )
                    except Exception as exc:
                        create_log(config, BotLog.Level.ERROR,
                            f"Scale-in failed: {exc}. Continuing with partial position.")
                if open_trade.partial_entry_filled:
                    create_log(config, BotLog.Level.INFO,
                        f"Scale-in: added {float(remaining_qty):.5f} at {price_f:.6f} "
                        f"(price confirmed {'above' if open_trade.side == Trade.Side.LONG else 'below'} MA7).")

        tp3_trail = float(config.tp3_trailing_percent)
        early_be = float(config.early_breakeven_r)
        lock_pr = float(config.lock_profit_r)
        # Snapshot flags before update to detect SL step transitions
        _was_early_be = open_trade.early_breakeven_moved
        _was_be = open_trade.breakeven_moved
        _was_lock = open_trade.profit_lock_moved
        _old_sl = open_trade.stop_loss
        if open_trade.is_paper:
            PaperTradingService.update_trade(
                open_trade,
                metrics["price"],
                signal_indicators.atr,
                float(config.trailing_atr_multiplier) if config.use_trailing_stop else 0,
                tp3_trailing_percent=tp3_trail,
                early_breakeven_r=early_be,
                lock_profit_r=lock_pr,
            )
        else:
            credential = getattr(config.user, "binance_credential", None)
            LiveTradingService(credential, config).update_trade(
                open_trade,
                metrics["price"],
                signal_indicators.atr,
                float(config.trailing_atr_multiplier) if config.use_trailing_stop else 0,
                tp3_trailing_percent=tp3_trail,
            )
        # Log SL step events
        if open_trade.status == Trade.Status.OPEN:
            price_now = float(metrics["price"])
            new_sl = float(open_trade.stop_loss)
            if not _was_early_be and open_trade.early_breakeven_moved:
                create_log(config, BotLog.Level.INFO,
                    f"SL moved to {new_sl:.6f} (early risk reduction at {early_be}R). "
                    f"Price {price_now:.6f}.")
            elif not _was_be and open_trade.breakeven_moved:
                create_log(config, BotLog.Level.INFO,
                    f"SL moved to breakeven {new_sl:.6f} (1R reached). "
                    f"Price {price_now:.6f}.")
            elif not _was_lock and open_trade.profit_lock_moved:
                locked_r = lock_pr - 1
                create_log(config, BotLog.Level.INFO,
                    f"SL moved to {new_sl:.6f} ({locked_r:.2f}R locked in at {lock_pr}R). "
                    f"Price {price_now:.6f}.")
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

    # Consecutive-loss circuit breaker
    if config.max_consecutive_losses > 0:
        losses = _consecutive_losses(config)
        if losses >= config.max_consecutive_losses:
            last_loss = (
                Trade.objects.filter(
                    user=config.user,
                    symbol=config.symbol,
                    status=Trade.Status.CLOSED,
                    realized_pnl__lt=0,
                )
                .order_by("-closed_at")
                .first()
            )
            if last_loss and last_loss.closed_at:
                elapsed_h = (timezone.now() - last_loss.closed_at).total_seconds() / 3600
                cooldown_h = float(config.circuit_breaker_hours)
                if elapsed_h < cooldown_h:
                    remaining_h = cooldown_h - elapsed_h
                    create_log(config, BotLog.Level.WARNING,
                        f"Circuit breaker: {losses} consecutive losses on {config.symbol}. "
                        f"New entries blocked for {remaining_h:.1f}h more.")
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

    # Auto-suppress symbols with poor historical win rate
    if config.auto_suppress_losing_symbols and _is_symbol_losing(config):
        create_log(
            config,
            BotLog.Level.INFO,
            f"Entry skipped: {config.symbol} has <40% win rate over its last 20 trades.",
        )
        return

    # Minimum confidence filter
    if config.min_confidence_to_trade > 0:
        confidence_score = int(snapshot.payload.get("confidence_score", 0))
        if confidence_score < config.min_confidence_to_trade:
            create_log(
                config,
                BotLog.Level.INFO,
                f"Entry skipped: confidence {confidence_score} is below minimum "
                f"{config.min_confidence_to_trade}.",
            )
            return

    # Volatility spike filter
    if float(config.atr_spike_max_ratio) > 0 and signal_indicators.atr_ma20 > 0:
        ratio = signal_indicators.atr / signal_indicators.atr_ma20
        if ratio > float(config.atr_spike_max_ratio):
            create_log(config, BotLog.Level.INFO,
                f"Entry skipped: ATR spike ({ratio:.2f}× ATR MA20) exceeds max "
                f"{float(config.atr_spike_max_ratio):.1f}×.")
            return

    # Funding rate filter
    if float(config.funding_rate_threshold) > 0:
        funding = float(metrics["funding_rate"])
        threshold = float(config.funding_rate_threshold)
        if signal.signal == "LONG" and funding > threshold:
            create_log(config, BotLog.Level.INFO,
                f"Entry skipped: funding rate {funding:.6f} is too high for LONG "
                f"(max {threshold:.6f}).")
            return
        if signal.signal == "SHORT" and funding < -threshold:
            create_log(config, BotLog.Level.INFO,
                f"Entry skipped: funding rate {funding:.6f} is too negative for SHORT "
                f"(min -{threshold:.6f}).")
            return

    # Multi-timeframe alignment score
    if config.min_tf_alignment_score > 0:
        tf_score = snapshot.payload.get("tf_alignment_score", 0)
        if tf_score < config.min_tf_alignment_score:
            create_log(config, BotLog.Level.INFO,
                f"Entry skipped: TF alignment score {tf_score}/3 is below "
                f"minimum {config.min_tf_alignment_score}.")
            return

    # Re-entry cooldown after stop loss
    if config.sl_cooldown_candles > 0:
        last_sl = (
            Trade.objects.filter(
                user=config.user,
                symbol=config.symbol,
                status=Trade.Status.CLOSED,
                close_reason__icontains="stop",
            )
            .order_by("-closed_at")
            .first()
        )
        if last_sl and last_sl.closed_at:
            tf_min = _timeframe_minutes(config.timeframe_signal)
            elapsed_candles = (timezone.now() - last_sl.closed_at).total_seconds() / 60 / tf_min
            if elapsed_candles < config.sl_cooldown_candles:
                remaining = int(config.sl_cooldown_candles - elapsed_candles) + 1
                create_log(config, BotLog.Level.INFO,
                    f"Entry skipped: re-entry cooldown active after stop loss "
                    f"({remaining} candle(s) remaining).")
                return

    # Volume spike filter — signal candle must show strong volume
    if float(config.volume_spike_multiplier) > 0 and signal_indicators.volume_ma20 > 0:
        volume_ratio = signal_indicators.volume / signal_indicators.volume_ma20
        if volume_ratio < float(config.volume_spike_multiplier):
            create_log(config, BotLog.Level.INFO,
                f"Entry skipped: signal candle volume ({volume_ratio:.2f}× MA20) is below "
                f"the {float(config.volume_spike_multiplier):.1f}× spike minimum.")
            return

    # MA7 slope filter — require trend momentum in signal direction
    if float(config.ma_slope_min_pct) > 0:
        ma7_slope = snapshot.payload.get("ma7_slope_pct", 0)
        required = float(config.ma_slope_min_pct)
        if signal.signal == "LONG" and ma7_slope < required:
            create_log(config, BotLog.Level.INFO,
                f"Entry skipped: MA7 slope ({ma7_slope:+.4f}%/candle) is below "
                f"minimum +{required:.4f}%/candle (trend too flat for LONG).")
            return
        if signal.signal == "SHORT" and ma7_slope > -required:
            create_log(config, BotLog.Level.INFO,
                f"Entry skipped: MA7 slope ({ma7_slope:+.4f}%/candle) is above "
                f"-{required:.4f}%/candle (trend too flat for SHORT).")
            return

    execution_payload = snapshot.payload
    effective_leverage = int(execution_payload.get("effective_leverage") or config.leverage)
    tp_r_multiple = float(execution_payload.get("tp_r_multiple") or config.atr_multiplier_tp)

    # Dynamic TP based on ADX strength
    if config.adx_tp_high_threshold > 0 and signal_indicators.adx >= config.adx_tp_high_threshold:
        tp_r_multiple = min(round(tp_r_multiple * 1.33, 2), 6.0)
    elif config.adx_tp_low_threshold > 0 and signal_indicators.adx <= config.adx_tp_low_threshold:
        tp_r_multiple = max(round(tp_r_multiple * 0.67, 2), 1.5)
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
    # Compute initial entry quantity (partial entry scaling)
    initial_quantity = plan.quantity
    is_partial = config.partial_entry_enabled
    if is_partial:
        pct = float(config.partial_entry_size_pct)
        initial_quantity = plan.quantity * Decimal(str(pct / 100))

    if live_service:
        try:
            order = live_service.place_entry(
                signal.signal,
                initial_quantity,
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
        executed_quantity = Decimal(str(order.get("executedQty") or initial_quantity))
        trade = Trade.objects.create(
            user=config.user,
            symbol=config.symbol,
            side=signal.signal,
            entry_price=executed_price,
            quantity=executed_quantity,
            remaining_quantity=executed_quantity,
            leverage=effective_leverage,
            stop_loss=plan.stop_loss,
            initial_stop_loss=plan.stop_loss,
            take_profit_1=plan.take_profit_1,
            take_profit_2=plan.take_profit_2,
            take_profit_3=plan.take_profit_3,
            open_reason=", ".join(signal.reasons),
            setup_tags=trade_setup_tags,
            replay_payload=replay_payload,
            is_paper=False,
            partial_entry_filled=not is_partial,
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
            quantity_override=initial_quantity if is_partial else None,
        )
    sizing_message = (
        f"{position_margin:.2f} USDT margin "
        f"({plan.risk_amount:.2f} USDT at stop)"
        if position_margin is not None
        else f"{signal.risk_multiplier:.0%} risk ({plan.risk_amount:.2f} USDT)"
    )
    partial_note = f" [{float(config.partial_entry_size_pct):.0f}% partial — waiting for MA7 confirm]" if is_partial else ""
    create_log(
        config,
        BotLog.Level.INFO,
        f"{'Live' if use_live else 'Paper'} {signal.signal} opened at {price:.6f} "
        f"with {sizing_message}, x{effective_leverage}, {snapshot.payload.get('regime_label', 'Manual')} regime, "
        f"TP {tp_r_multiple:.2f}R, grade {snapshot.payload.get('trade_grade', 'D')}, "
        f"confidence {snapshot.payload.get('confidence_score', 0)}{partial_note}.",
    )
    broadcast_user_update(config.user_id, "position", TradeSerializer(trade).data)


@shared_task
def auto_register_top_movers() -> None:
    for settings_obj in AutoScannerSettings.objects.filter(enabled=True).select_related("user"):
        try:
            sync_top_movers_to_scanner(settings_obj.user, settings_obj.top_n, settings_obj.quote_asset)
        except Exception:
            logger.exception("Failed to sync top movers for user %s", settings_obj.user_id)


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
