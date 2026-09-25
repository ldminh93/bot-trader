from django.contrib.auth import get_user_model

from ..models import BotLog, CoinCatalog, Trade, TradingBotConfig
from .discord_alert_service import send_discord_alert
from .websocket_service import broadcast_user_update

User = get_user_model()


def _log_mirror_event(user, symbol: str, message: str, level: str = BotLog.Level.INFO) -> None:
    from ..serializers import BotLogSerializer

    log = BotLog.objects.create(
        user=user, symbol=symbol, level=level, category=BotLog.Category.SCANNER, message=message
    )
    broadcast_user_update(user.id, "log", BotLogSerializer(log).data)
    send_discord_alert(user, symbol, level, message, category="scanner_membership")


def mirror_admin_coins_to_regular_users() -> dict:
    """Force every regular (non-staff) user's coin list — and each coin's
    scanning on/off state — to exactly match any admin (staff user)'s current
    setup.

    Called after an admin manually adds a coin (BotConfigView.post) and after
    an admin's top-mover sync (sync_top_movers_to_scanner). Regular users can
    no longer add or remove coins themselves (BotConfigView.post/delete are
    admin-only), so this is the only thing that keeps their scanner coins —
    and whether each one is actively scanning — in sync with admin, fully
    hands-off. A coin's scanning state is force-matched every run (a regular
    user's own Pause/Scan click on a mirrored coin will be overwritten by the
    next sync).

    Same open-position protection sync_top_movers_to_scanner applies to admin's
    own coins applies per regular user here too, since a paused (is_running=
    False) config is never processed by run_active_bots — pausing one out from
    under an open position would stop the bot from managing it. So a coin
    is never removed, and never paused (True -> False), while that specific
    user has an open position on it; both are skipped until the position
    closes and a later sync catches it.
    """
    admin_status: dict[str, dict] = {}
    for cfg in TradingBotConfig.objects.filter(user__is_staff=True).order_by("symbol", "-is_running"):
        admin_status.setdefault(
            cfg.symbol, {"is_running": cfg.is_running, "top_mover_side": cfg.top_mover_side}
        )
    admin_symbols = set(admin_status.keys())
    for symbol in admin_symbols:
        CoinCatalog.objects.get_or_create(symbol=symbol)

    added: dict[int, list[str]] = {}
    updated: dict[int, list[str]] = {}
    removed: dict[int, list[str]] = {}
    skipped: dict[int, list[str]] = {}

    for user in User.objects.filter(is_staff=False):
        existing = {c.symbol: c for c in TradingBotConfig.objects.filter(user=user)}
        existing_symbols = set(existing.keys())
        open_position_symbols = set(
            Trade.objects.filter(user=user, status=Trade.Status.OPEN).values_list("symbol", flat=True)
        )

        missing = admin_symbols - existing_symbols
        if missing:
            defaults = TradingBotConfig.account_wide_defaults(user)
            for symbol in missing:
                status = admin_status[symbol]
                TradingBotConfig.objects.create(
                    user=user,
                    symbol=symbol,
                    admin_mirrored=True,
                    is_running=status["is_running"],
                    top_mover_side=status["top_mover_side"],
                    **defaults,
                )
                _log_mirror_event(
                    user,
                    symbol,
                    "Coin added to scanner (mirrored from admin)."
                    if status["is_running"]
                    else "Coin configuration added (mirrored from admin).",
                )
            added[user.id] = sorted(missing)

        user_updated = []
        user_skipped = []
        for symbol in admin_symbols & existing_symbols:
            config = existing[symbol]
            status = admin_status[symbol]
            target_is_running = status["is_running"]
            if config.is_running and not target_is_running and symbol in open_position_symbols:
                # Don't pause a coin out from under this user's own open
                # position — run_active_bots skips is_running=False configs
                # entirely, which would stop managing it mid-trade.
                target_is_running = True
                user_skipped.append(symbol)

            changed_fields = []
            if config.is_running != target_is_running:
                config.is_running = target_is_running
                changed_fields.append("is_running")
            if config.top_mover_side != status["top_mover_side"]:
                config.top_mover_side = status["top_mover_side"]
                changed_fields.append("top_mover_side")
            if changed_fields:
                config.save(update_fields=changed_fields)
                user_updated.append(symbol)
                if "is_running" in changed_fields:
                    _log_mirror_event(
                        user,
                        symbol,
                        "Scanning started (mirrored from admin)."
                        if target_is_running
                        else "Scanning paused (mirrored from admin).",
                    )
                else:
                    _log_mirror_event(user, symbol, "Top-mover side updated (mirrored from admin).")
        if user_updated:
            updated[user.id] = sorted(user_updated)

        stale = existing_symbols - admin_symbols
        user_removed = []
        for symbol in stale:
            if symbol in open_position_symbols:
                user_skipped.append(symbol)
                continue
            existing[symbol].delete()
            user_removed.append(symbol)
            _log_mirror_event(user, symbol, "Coin removed from scanner (no longer tracked by admin).")
        if user_removed:
            removed[user.id] = sorted(user_removed)
        if user_skipped:
            skipped[user.id] = sorted(user_skipped)

    return {"added": added, "updated": updated, "removed": removed, "skipped": skipped}
