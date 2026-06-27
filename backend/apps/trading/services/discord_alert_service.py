import httpx
from django.utils import timezone
from datetime import timedelta

from apps.trading.models import BotLog, UserDiscordAlertConfig

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


def _recent_error_count(user, symbol: str, message: str, window_minutes: int) -> int:
    since = timezone.now() - timedelta(minutes=window_minutes)
    return BotLog.objects.filter(
        user=user,
        symbol=symbol,
        level=BotLog.Level.ERROR,
        message=message,
        created_at__gte=since,
    ).count()
