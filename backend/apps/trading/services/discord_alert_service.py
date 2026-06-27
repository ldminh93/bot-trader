from datetime import timedelta
from decimal import Decimal

import httpx
from django.utils import timezone

from apps.trading.models import BotLog, Trade, UserDiscordAlertConfig

from .credential_service import decrypt_secret


def _should_notify(config: UserDiscordAlertConfig, level: str, force: bool = False) -> bool:
    if not config.webhook_url_encrypted:
        return False
    if force:
        return True
    if not config.is_enabled:
        return False
    return (
        (level == BotLog.Level.INFO and config.notify_info)
        or (level == BotLog.Level.WARNING and config.notify_warning)
        or (level == BotLog.Level.ERROR and config.notify_error)
    )


def send_discord_alert(user, symbol: str, level: str, message: str, force: bool = False) -> None:
    config = getattr(user, "discord_alert_config", None)
    if not config or not _should_notify(config, level, force):
        return
    repeat_count = 1
    if level == BotLog.Level.ERROR and config.error_escalation_enabled and not force:
        repeat_count = _recent_error_count(
            user,
            symbol,
            message,
            int(config.error_escalation_window_minutes),
        )
        threshold = int(config.error_escalation_threshold)
        if repeat_count < threshold or repeat_count % threshold != 0:
            return
    try:
        webhook_url = decrypt_secret(config.webhook_url_encrypted)
    except ValueError:
        return
    prefix = f"[{level}]"
    if level == BotLog.Level.ERROR and repeat_count > 1:
        prefix = f"[{level} x{repeat_count}]"
    payload = {
        "username": "Bot Trader",
        "content": f"{prefix} {symbol}: {message}",
    }
    try:
        httpx.post(webhook_url, json=payload, timeout=4)
    except httpx.HTTPError:
        return


def send_trade_replay_export(trade: Trade, force: bool = False) -> bool:
    config = getattr(trade.user, "discord_alert_config", None)
    if not config or not _should_notify(config, BotLog.Level.INFO, force):
        return False
    try:
        webhook_url = decrypt_secret(config.webhook_url_encrypted)
    except ValueError:
        return False

    replay = trade.replay_payload or {}
    grade = replay.get("trade_grade", _tag_value(trade.setup_tags or [], "grade") or "D")
    confidence = replay.get("confidence_score", 0)
    regime = replay.get("regime_label") or replay.get("regime") or "Unknown"
    reasons = replay.get("reasons") or [trade.open_reason]
    margin_basis = trade.entry_price * trade.quantity / Decimal(trade.leverage) if trade.leverage else Decimal("0")
    margin_roi = trade.realized_pnl / margin_basis * Decimal("100") if margin_basis else Decimal("0")
    color = 0x43C987 if trade.realized_pnl > 0 else 0xF06464 if trade.realized_pnl < 0 else 0xF0B90B
    payload = {
        "username": "Bot Trader",
        "content": f"Trade replay export: {trade.symbol} {trade.side} grade {grade}",
        "embeds": [
            {
                "title": f"{trade.symbol} {trade.side} replay",
                "color": color,
                "fields": [
                    {"name": "PnL", "value": f"{trade.realized_pnl:.4f} USDT ({margin_roi:.2f}% margin ROI)", "inline": True},
                    {"name": "Entry / Exit", "value": f"{trade.entry_price} -> {trade.exit_price or '-'}", "inline": True},
                    {"name": "Grade", "value": f"{grade} / confidence {confidence}", "inline": True},
                    {"name": "Regime", "value": str(regime), "inline": True},
                    {"name": "Leverage", "value": f"x{trade.leverage}", "inline": True},
                    {"name": "Close reason", "value": trade.close_reason or "-", "inline": False},
                    {"name": "Entry reasons", "value": "\n".join(str(reason) for reason in reasons[:5])[:1000], "inline": False},
                ],
            }
        ],
    }
    try:
        response = httpx.post(webhook_url, json=payload, timeout=5)
        return response.status_code < 400
    except httpx.HTTPError:
        return False


def _recent_error_count(user, symbol: str, message: str, window_minutes: int) -> int:
    since = timezone.now() - timedelta(minutes=window_minutes)
    return BotLog.objects.filter(
        user=user,
        symbol=symbol,
        level=BotLog.Level.ERROR,
        message=message,
        created_at__gte=since,
    ).count()


def _tag_value(tags: list[str], prefix: str) -> str | None:
    for tag in tags:
        text = str(tag)
        if text.startswith(f"{prefix}:"):
            return text.split(":", 1)[1]
    return None
