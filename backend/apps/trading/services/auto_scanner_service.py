from ..models import AutoScannerSettings, BotLog, Trade, TradingBotConfig
from .binance_service import BinanceService
from .discord_alert_service import send_discord_alert
from .websocket_service import broadcast_user_update


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

    movers = BinanceService().fetch_top_movers(limit=limit, quote_asset=quote)
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
        return {"added": [], "removed": [], "skipped": []}

    added: list[str] = []
    removed: list[str] = []
    skipped: list[str] = []

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

    for symbol, (side, price_change_percent) in desired.items():
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
                "position_margin_usdt": 10,
                "leverage": 3,
                "live_mode_requested": account_live_mode,
                # These two default to True on the model for manually-configured
                # coins, but a freshly auto-registered top-mover coin hasn't been
                # reviewed by the operator yet — don't silently gate/restrict it
                # with settings they never chose.
                "auto_suppress_losing_tags": False,
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

    return {"added": added, "removed": removed, "skipped": skipped}
