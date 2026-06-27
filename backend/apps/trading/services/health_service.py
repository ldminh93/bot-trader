from decimal import Decimal

from django.conf import settings

from apps.trading.models import Trade, TradingBotConfig

from .binance_service import BinanceService
from .credential_service import decrypt_secret


def build_live_sync_health(user) -> dict:
    configs = list(TradingBotConfig.objects.filter(user=user).order_by("symbol"))
    open_trades = {
        trade.symbol: trade
        for trade in Trade.objects.filter(user=user, status=Trade.Status.OPEN)
    }
    credential = getattr(user, "binance_credential", None)
    can_check_exchange = bool(settings.ENABLE_LIVE_TRADING and credential and credential.is_active)
    client = None
    if can_check_exchange:
        try:
            client = BinanceService(
                api_key=credential.api_key,
                api_secret=decrypt_secret(credential.api_secret_encrypted),
            )
        except ValueError:
            client = None

    rows = []
    mismatches = 0
    for config in configs:
        trade = open_trades.get(config.symbol)
        exchange_quantity = Decimal("0")
        exchange_available = False
        if client and config.live_mode_requested:
            try:
                exchange_quantity = client.position_amount(config.symbol)
                exchange_available = True
            except Exception:
                exchange_available = False

        if trade and trade.is_paper:
            status = "paper_open"
            detail = "Paper trade is open; exchange sync is not required."
        elif trade and exchange_available and exchange_quantity <= 0:
            status = "mismatch"
            detail = "Bot has an open live trade, but Binance reports no position."
            mismatches += 1
        elif not trade and exchange_available and exchange_quantity > 0:
            status = "mismatch"
            detail = "Binance has an open position, but the bot has no open trade."
            mismatches += 1
        elif trade:
            status = "synced" if exchange_available else "unknown"
            detail = "Bot and Binance both show an open position." if exchange_available else "Exchange check unavailable."
        elif exchange_available:
            status = "synced"
            detail = "No open bot trade or Binance position."
        else:
            status = "not_checked"
            detail = "Live sync only checks symbols with live mode and valid credentials."

        rows.append(
            {
                "symbol": config.symbol,
                "is_running": config.is_running,
                "live_mode_requested": config.live_mode_requested,
                "bot_open": bool(trade),
                "bot_trade_id": trade.id if trade else None,
                "bot_is_paper": trade.is_paper if trade else None,
                "exchange_open": exchange_quantity > 0,
                "exchange_quantity": str(exchange_quantity),
                "status": status,
                "detail": detail,
            }
        )

    return {
        "enabled": bool(settings.ENABLE_LIVE_TRADING),
        "credential_ready": bool(client),
        "mismatches": mismatches,
        "rows": rows,
    }
