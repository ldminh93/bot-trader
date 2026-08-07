from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import BotLog, UserDiscordAlertConfig
from apps.trading.services.credential_service import encrypt_secret
from apps.trading.services.discord_alert_service import send_discord_alert


def _config(user, **overrides) -> UserDiscordAlertConfig:
    defaults = {
        "webhook_url_encrypted": encrypt_secret("https://discord.example/webhook"),
        "is_enabled": True,
        "notify_info": True,
        "notify_warning": True,
        "notify_error": True,
        "notify_scanner_changes": True,
    }
    defaults.update(overrides)
    return UserDiscordAlertConfig.objects.create(user=user, **defaults)


@pytest.mark.django_db
@patch("apps.trading.services.discord_alert_service.httpx.post")
def test_scanner_membership_alert_respects_its_own_toggle_even_when_info_enabled(mock_post):
    """
    Reproduces the reported annoyance: scanner add/remove churn used to ride
    the general Info toggle, so muting it also muted every other Info-level
    alert. It must have its own independent opt-out.
    """
    user = get_user_model().objects.create_user("scanner-mute@example.com", password="secure-pass")
    _config(user, notify_info=True, notify_scanner_changes=False)

    send_discord_alert(
        user, "BTCUSDT", BotLog.Level.INFO, "Coin auto-registered", category="scanner_membership"
    )

    mock_post.assert_not_called()


@pytest.mark.django_db
@patch("apps.trading.services.discord_alert_service.httpx.post")
def test_scanner_membership_alert_fires_when_enabled(mock_post):
    user = get_user_model().objects.create_user("scanner-notify@example.com", password="secure-pass")
    _config(user, notify_scanner_changes=True)

    send_discord_alert(
        user, "BTCUSDT", BotLog.Level.INFO, "Coin auto-registered", category="scanner_membership"
    )

    mock_post.assert_called_once()


@pytest.mark.django_db
@patch("apps.trading.services.discord_alert_service.httpx.post")
def test_other_info_alerts_are_unaffected_by_scanner_toggle(mock_post):
    """Muting scanner churn must not silence unrelated Info-level alerts (e.g.
    trade lifecycle events), since they don't pass category="scanner_membership"."""
    user = get_user_model().objects.create_user("scanner-mute-other@example.com", password="secure-pass")
    _config(user, notify_info=True, notify_scanner_changes=False)

    send_discord_alert(user, "BTCUSDT", BotLog.Level.INFO, "Entry skipped: some reason")

    mock_post.assert_called_once()
