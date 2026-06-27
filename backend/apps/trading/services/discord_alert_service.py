import httpx

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
    try:
        webhook_url = decrypt_secret(config.webhook_url_encrypted)
    except ValueError:
        return
    payload = {
        "username": "Bot Trader",
        "content": f"[{level}] {symbol}: {message}",
    }
    try:
        httpx.post(webhook_url, json=payload, timeout=4)
    except httpx.HTTPError:
        return
