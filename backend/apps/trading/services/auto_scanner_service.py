from ..models import AutoScannerSettings, BotLog, Trade, TradingBotConfig
from .binance_service import BinanceService
from .discord_alert_service import send_discord_alert
from .websocket_service import broadcast_user_update

# calculate_indicators() (indicator_service.py) requires at least this many
# candles and raises ValueError otherwise — a symbol newly listed on Binance
# may not have this much klines history yet. Checked here so a brand-new
# top-mover coin without enough history isn't registered only to have every
# subsequent bot cycle fail with "At least 100 candles are required" until
# Binance accumulates enough candles for it.
MIN_CANDLES_REQUIRED = 100


def log_scanner_event(
    user,
    symbol: str,
    message: str,
    level: str = BotLog.Level.INFO,
    category: str | None = None,
) -> None:
    from ..serializers import BotLogSerializer

    log = BotLog.objects.create(user=user, symbol=symbol, level=level, message=message)
    broadcast_user_update(user.id, "log", BotLogSerializer(log).data)
    send_discord_alert(user, symbol, level, message, category=category)


def sync_top_movers_to_scanner(user, top_n: int | None = None, quote_asset: str | None = None) -> dict:
    from django.utils import timezone
    settings_obj, _ = AutoScannerSettings.objects.get_or_create(user=user)
    limit = top_n or settings_obj.top_n
    quote = (quote_asset or settings_obj.quote_asset).upper()

    binance = BinanceService()
    movers = binance.fetch_top_movers(limit=limit, quote_asset=quote)
    desired: dict[str, tuple[str, float]] = {}
    for side, items in (("gainer", movers["gainers"]), ("loser", movers["losers"])):
        for item in items:
            desired[item["symbol"]] = (side, item["price_change_percent"])

    if not desired:
        # Binance's public 24hr-ticker fetch swallows HTTP/parsing failures and
        # returns an empty list (see BinanceService._fetch_24hr_tickers), which
        # would otherwise look identical to "no gainers or losers exist" —
        # impossible on a live USDT-M futures market. Treat an empty result as
        # a failed fetch and leave the existing scanner list untouched instead
        # of deleting every auto-registered coin because none matched an empty
        # "desired" set.
        log_scanner_event(
            user,
            "SCANNER",
            "Top-movers sync skipped: Binance returned no gainers/losers data "
            "(likely a transient fetch failure) — existing scanner coins were left unchanged.",
            level=BotLog.Level.WARNING,
        )
        return {"added": [], "removed": [], "skipped": [], "ignored_new_listings": []}

    added: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []
    ignored_new_listings: list[str] = []

    stale_configs = TradingBotConfig.objects.filter(user=user, auto_registered=True).exclude(
        symbol__in=desired.keys()
    )
    for config in stale_configs:
        has_open_position = Trade.objects.filter(
            user=user, symbol=config.symbol, status=Trade.Status.OPEN
        ).exists()
        if has_open_position:
            skipped.append(config.symbol)
            continue
        symbol = config.symbol
        config.delete()
        removed.append(symbol)
        log_scanner_event(
            user,
            symbol,
            "Coin removed from scanner (no longer a top gainer/loser).",
            category="scanner_membership",
        )

    # Mirrors BotConfigView.post's manual-add behavior: a freshly auto-registered
    # coin should inherit the account's current live-trading state rather than
    # falling back to the live_mode_requested model default (False) — otherwise
    # every auto-added coin silently starts paper-only even when the operator
    # already has live trading enabled account-wide for every other coin.
    account_live_mode = TradingBotConfig.objects.filter(user=user, live_mode_requested=True).exists()
    # position_margin_usdt, confidence_leverage_enabled, min_effective_leverage,
    # and auto_suppress_losing_tags/symbols are account-wide (see
    # TradingBotConfig.ACCOUNT_WIDE_FIELDS) — a newly auto-registered coin should
    # match whatever every other coin already has, not a hardcoded per-coin
    # default. account_wide_defaults() is empty only when this is the very first
    # coin ever registered for the account, in which case the literal fallbacks
    # below apply (10 USDT margin, auto-suppress-tags off since nothing has been
    # reviewed by the operator yet).
    account_defaults = TradingBotConfig.account_wide_defaults(user)

    already_tracked = set(
        TradingBotConfig.objects.filter(user=user, symbol__in=desired.keys()).values_list(
            "symbol", flat=True
        )
    )

    for symbol, (side, price_change_percent) in desired.items():
        if symbol not in already_tracked:
            # Auto-registered configs get the model's default timeframe_signal
            # ("15m") and timeframe_trend ("1h") — see the get_or_create defaults
            # below, which don't override either field. A coarser interval covers
            # less wall-clock history per candle, so "1h" is the tighter
            # constraint for a freshly-listed symbol: it can fail this check
            # while "15m" alone would pass. Check both so registration accurately
            # predicts what process_config's first cycle will be able to fetch.
            insufficient_history = False
            min_available = None
            for interval in ("15m", "1h"):
                candles = binance.fetch_klines(symbol, interval, limit=MIN_CANDLES_REQUIRED)
                if len(candles) < MIN_CANDLES_REQUIRED:
                    insufficient_history = True
                    min_available = len(candles) if min_available is None else min(min_available, len(candles))
            if insufficient_history:
                ignored_new_listings.append(symbol)
                log_scanner_event(
                    user,
                    symbol,
                    f"Ignored top-{side} ({price_change_percent:.2f}%): only {min_available} candles of "
                    f"history available on Binance (need {MIN_CANDLES_REQUIRED}) — likely a newly-listed "
                    "pair. Will retry on a future sync once enough history exists.",
                    level=BotLog.Level.WARNING,
                    category="scanner_membership",
                )
                continue

        config, created = TradingBotConfig.objects.get_or_create(
            user=user,
            symbol=symbol,
            defaults={
                "auto_registered": True,
                "is_running": True,
                "top_mover_side": side,
                "require_confirmed_higher_tf": True,
                "require_ma7_slope_confirmation": True,
                "require_funding_confirmation": True,
                "position_margin_usdt": account_defaults.get("position_margin_usdt", 10),
                "leverage": 3,
                "live_mode_requested": account_live_mode,
                "confidence_leverage_enabled": account_defaults.get("confidence_leverage_enabled", True),
                "min_effective_leverage": account_defaults.get("min_effective_leverage", 0),
                # These two default to True on the model for manually-configured
                # coins, but a freshly auto-registered top-mover coin hasn't been
                # reviewed by the operator yet — don't silently gate/restrict it
                # with settings they never chose, unless the account already has
                # a shared preference set from other coins.
                "auto_suppress_losing_tags": account_defaults.get("auto_suppress_losing_tags", False),
                "auto_suppress_losing_symbols": account_defaults.get("auto_suppress_losing_symbols", False),
                "daily_loss_limit_enabled": False,
            },
        )
        if created:
            added.append(symbol)
            log_scanner_event(
                user,
                symbol,
                f"Coin auto-registered and scanning started from top {side} ({price_change_percent:.2f}%).",
                category="scanner_membership",
            )
            continue

        if not config.auto_registered:
            continue

        update_fields = []
        if config.top_mover_side != side:
            config.top_mover_side = side
            update_fields.append("top_mover_side")
        if not config.is_running:
            config.is_running = True
            update_fields.append("is_running")
            added.append(symbol)
            log_scanner_event(
                user,
                symbol,
                f"Scanning started for auto-registered coin (top {side}, {price_change_percent:.2f}%).",
                category="scanner_membership",
            )
        if update_fields:
            config.save(update_fields=update_fields)

    settings_obj.last_synced_at = timezone.now()
    settings_obj.save(update_fields=["last_synced_at"])

    return {
        "added": added,
        "removed": removed,
        "skipped": skipped,
        "ignored_new_listings": ignored_new_listings,
    }
