from ..models import AutoScannerSettings, BotLog, Trade, TradingBotConfig
from .binance_service import BinanceService
from .discord_alert_service import send_discord_alert
from .websocket_service import broadcast_user_update


def _log(user, symbol: str, message: str) -> None:
    from ..serializers import BotLogSerializer

    log = BotLog.objects.create(user=user, symbol=symbol, level=BotLog.Level.INFO, message=message)
    broadcast_user_update(user.id, "log", BotLogSerializer(log).data)
    send_discord_alert(user, symbol, BotLog.Level.INFO, message)


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
        _log(user, symbol, "Coin removed from scanner (no longer a top gainer/loser).")

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
            },
        )
        if created:
            added.append(symbol)
            _log(
                user,
                symbol,
                f"Coin auto-registered and scanning started from top {side} ({price_change_percent:.2f}%).",
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
            _log(
                user,
                symbol,
                f"Scanning started for auto-registered coin (top {side}, {price_change_percent:.2f}%).",
            )
        if update_fields:
            config.save(update_fields=update_fields)

    settings_obj.last_synced_at = timezone.now()
    settings_obj.save(update_fields=["last_synced_at"])

    return {"added": added, "removed": removed, "skipped": skipped}
