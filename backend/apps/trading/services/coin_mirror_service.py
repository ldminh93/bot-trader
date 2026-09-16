from django.contrib.auth import get_user_model

from ..models import CoinCatalog, Trade, TradingBotConfig

User = get_user_model()


def mirror_admin_coins_to_regular_users() -> dict:
    """Keep every regular (non-staff) user's coin list in sync with the set of
    symbols any admin (staff user) currently has configured.

    Called after an admin manually adds a coin (BotConfigView.post) and after
    an admin's top-mover sync (sync_top_movers_to_scanner) — both additions
    and removals discovered there are mirrored onto every regular user, using
    each user's own account-wide defaults for any newly mirrored coin. Coins a
    regular user added themselves (admin_mirrored=False) are never touched,
    even if no admin currently has that symbol.
    """
    admin_symbols = set(
        TradingBotConfig.objects.filter(user__is_staff=True).values_list("symbol", flat=True)
    )
    for symbol in admin_symbols:
        CoinCatalog.objects.get_or_create(symbol=symbol)

    added: dict[int, list[str]] = {}
    removed: dict[int, list[str]] = {}

    for user in User.objects.filter(is_staff=False):
        existing_symbols = set(
            TradingBotConfig.objects.filter(user=user).values_list("symbol", flat=True)
        )
        missing = admin_symbols - existing_symbols
        if missing:
            defaults = TradingBotConfig.account_wide_defaults(user)
            for symbol in missing:
                TradingBotConfig.objects.create(
                    user=user, symbol=symbol, admin_mirrored=True, **defaults
                )
            added[user.id] = sorted(missing)

        stale_mirrored = TradingBotConfig.objects.filter(user=user, admin_mirrored=True).exclude(
            symbol__in=admin_symbols
        )
        user_removed = []
        for config in stale_mirrored:
            has_open_position = Trade.objects.filter(
                user=user, symbol=config.symbol, status=Trade.Status.OPEN
            ).exists()
            if has_open_position:
                continue
            user_removed.append(config.symbol)
            config.delete()
        if user_removed:
            removed[user.id] = sorted(user_removed)

    return {"added": added, "removed": removed}
