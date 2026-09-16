from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.models import CoinCatalog, Trade, TradingBotConfig
from apps.trading.services.auto_scanner_service import sync_top_movers_to_scanner
from apps.trading.services.coin_mirror_service import mirror_admin_coins_to_regular_users


def _movers(*symbols: str) -> dict:
    return {"gainers": [{"symbol": s, "price_change_percent": 1.0} for s in symbols], "losers": []}


def _candles(count: int = 100) -> list[dict]:
    return [{"close": 100.0} for _ in range(count)]


@pytest.fixture(autouse=True)
def _mock_mirror_broadcast():
    """mirror_admin_coins_to_regular_users logs via BotLog + a websocket
    broadcast (matching log_scanner_event's pattern) — the broadcast needs a
    real channel layer (Redis), which isn't available in tests, same reason
    the auto-scanner tests below mock out log_scanner_event entirely."""
    with patch("apps.trading.services.coin_mirror_service.broadcast_user_update"):
        yield


@pytest.mark.django_db
def test_mirror_adds_admin_coin_to_regular_user_with_their_own_defaults():
    admin = get_user_model().objects.create_user("mirror-admin@example.com", password="secure-pass", is_staff=True)
    regular = get_user_model().objects.create_user("mirror-regular@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT", leverage=25)
    TradingBotConfig.objects.create(user=regular, symbol="ETHUSDT", position_margin_usdt=42)

    result = mirror_admin_coins_to_regular_users()

    mirrored = TradingBotConfig.objects.get(user=regular, symbol="BTCUSDT")
    assert mirrored.admin_mirrored is True
    assert mirrored.position_margin_usdt == 42
    assert mirrored.leverage == 10
    assert result["added"] == {regular.id: ["BTCUSDT"]}
    assert CoinCatalog.objects.filter(symbol="BTCUSDT").exists()


@pytest.mark.django_db
def test_mirror_removes_stale_admin_mirrored_coin():
    admin = get_user_model().objects.create_user("mirror-admin2@example.com", password="secure-pass", is_staff=True)
    regular = get_user_model().objects.create_user("mirror-regular2@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT")
    TradingBotConfig.objects.create(user=regular, symbol="ETHUSDT", admin_mirrored=True)

    result = mirror_admin_coins_to_regular_users()

    assert not TradingBotConfig.objects.filter(user=regular, symbol="ETHUSDT").exists()
    assert result["removed"] == {regular.id: ["ETHUSDT"]}


@pytest.mark.django_db
def test_mirror_removes_legacy_coin_a_regular_user_added_before_the_lockdown():
    """Regular users can no longer add/remove coins themselves (BotConfigView
    is admin-only for POST/DELETE), so a coin a regular user has that no admin
    has is legacy drift — it's pruned too, regardless of admin_mirrored."""
    admin = get_user_model().objects.create_user("mirror-admin3@example.com", password="secure-pass", is_staff=True)
    regular = get_user_model().objects.create_user("mirror-regular3@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT")
    TradingBotConfig.objects.create(user=regular, symbol="ETHUSDT", admin_mirrored=False)

    result = mirror_admin_coins_to_regular_users()

    assert not TradingBotConfig.objects.filter(user=regular, symbol="ETHUSDT").exists()
    assert result["removed"] == {regular.id: ["ETHUSDT"]}


@pytest.mark.django_db
def test_mirror_skips_removal_with_open_position():
    admin = get_user_model().objects.create_user("mirror-admin4@example.com", password="secure-pass", is_staff=True)
    regular = get_user_model().objects.create_user("mirror-regular4@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT")
    TradingBotConfig.objects.create(user=regular, symbol="ETHUSDT", admin_mirrored=True)
    Trade.objects.create(
        user=regular,
        symbol="ETHUSDT",
        side=Trade.Side.LONG,
        status=Trade.Status.OPEN,
        entry_price=100,
        quantity=1,
        stop_loss=90,
        take_profit_1=110,
        take_profit_2=120,
        take_profit_3=130,
        open_reason="test",
    )

    result = mirror_admin_coins_to_regular_users()

    assert TradingBotConfig.objects.filter(user=regular, symbol="ETHUSDT").exists()
    assert result["removed"] == {}


@pytest.mark.django_db
def test_mirror_starts_scanning_on_a_coin_admin_has_running():
    admin = get_user_model().objects.create_user(
        "mirror-status-admin@example.com", password="secure-pass", is_staff=True
    )
    regular = get_user_model().objects.create_user("mirror-status-regular@example.com", password="secure-pass")
    TradingBotConfig.objects.create(
        user=admin, symbol="BTCUSDT", is_running=True, top_mover_side="gainer"
    )
    TradingBotConfig.objects.create(user=regular, symbol="BTCUSDT", is_running=False, top_mover_side=None)

    result = mirror_admin_coins_to_regular_users()

    mirrored = TradingBotConfig.objects.get(user=regular, symbol="BTCUSDT")
    assert mirrored.is_running is True
    assert mirrored.top_mover_side == "gainer"
    assert result["updated"] == {regular.id: ["BTCUSDT"]}


@pytest.mark.django_db
def test_mirror_pauses_scanning_when_admin_no_longer_running_it():
    admin = get_user_model().objects.create_user(
        "mirror-pause-admin@example.com", password="secure-pass", is_staff=True
    )
    regular = get_user_model().objects.create_user("mirror-pause-regular@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT", is_running=False)
    TradingBotConfig.objects.create(
        user=regular, symbol="BTCUSDT", is_running=True, top_mover_side="gainer", admin_mirrored=True
    )

    result = mirror_admin_coins_to_regular_users()

    mirrored = TradingBotConfig.objects.get(user=regular, symbol="BTCUSDT")
    assert mirrored.is_running is False
    assert result["updated"] == {regular.id: ["BTCUSDT"]}


@pytest.mark.django_db
def test_mirror_overrides_a_regular_users_own_pause_click():
    """'Always follow admin' means a regular user's manual Pause/Scan on a
    mirrored coin does not stick — the next mirror run re-forces admin's
    current state onto it."""
    admin = get_user_model().objects.create_user(
        "mirror-override-admin@example.com", password="secure-pass", is_staff=True
    )
    regular = get_user_model().objects.create_user("mirror-override-regular@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT", is_running=True)
    TradingBotConfig.objects.create(user=regular, symbol="BTCUSDT", is_running=False, admin_mirrored=True)

    mirror_admin_coins_to_regular_users()

    assert TradingBotConfig.objects.get(user=regular, symbol="BTCUSDT").is_running is True


@pytest.mark.django_db
def test_admin_adding_coin_via_api_mirrors_to_regular_users():
    admin = get_user_model().objects.create_user("api-admin@example.com", password="secure-pass", is_staff=True)
    regular = get_user_model().objects.create_user("api-regular@example.com", password="secure-pass")
    CoinCatalog.objects.create(symbol="BTCUSDT")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post("/api/bot/config", {"symbol": "BTCUSDT"}, format="json")

    assert response.status_code == 201
    assert TradingBotConfig.objects.filter(user=regular, symbol="BTCUSDT", admin_mirrored=True).exists()


@pytest.mark.django_db
def test_regular_user_cannot_add_coin_via_api_at_all():
    regular_a = get_user_model().objects.create_user("api-regular-a@example.com", password="secure-pass")
    regular_b = get_user_model().objects.create_user("api-regular-b@example.com", password="secure-pass")
    CoinCatalog.objects.create(symbol="BTCUSDT")
    client = APIClient()
    client.force_authenticate(regular_a)

    response = client.post("/api/bot/config", {"symbol": "BTCUSDT"}, format="json")

    assert response.status_code == 403
    assert not TradingBotConfig.objects.filter(user=regular_a, symbol="BTCUSDT").exists()
    assert not TradingBotConfig.objects.filter(user=regular_b, symbol="BTCUSDT").exists()


@pytest.mark.django_db
@patch("apps.trading.services.auto_scanner_service.log_scanner_event")
@patch("apps.trading.services.auto_scanner_service.BinanceService")
def test_admin_top_mover_sync_mirrors_to_regular_users(mock_binance_cls, mock_log):
    admin = get_user_model().objects.create_user("sync-admin@example.com", password="secure-pass", is_staff=True)
    regular = get_user_model().objects.create_user("sync-regular@example.com", password="secure-pass")
    mock_binance_cls.return_value.fetch_klines.return_value = _candles()
    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("BTCUSDT")

    sync_top_movers_to_scanner(admin, top_n=1, quote_asset="USDT")

    assert TradingBotConfig.objects.filter(user=regular, symbol="BTCUSDT", admin_mirrored=True).exists()


@pytest.mark.django_db
@patch("apps.trading.services.auto_scanner_service.log_scanner_event")
@patch("apps.trading.services.auto_scanner_service.BinanceService")
def test_regular_user_top_mover_sync_does_not_mirror_to_others(mock_binance_cls, mock_log):
    regular_a = get_user_model().objects.create_user("sync-regular-a@example.com", password="secure-pass")
    regular_b = get_user_model().objects.create_user("sync-regular-b@example.com", password="secure-pass")
    mock_binance_cls.return_value.fetch_klines.return_value = _candles()
    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("BTCUSDT")

    sync_top_movers_to_scanner(regular_a, top_n=1, quote_asset="USDT")

    assert not TradingBotConfig.objects.filter(user=regular_b, symbol="BTCUSDT").exists()


@pytest.mark.django_db
@patch("apps.trading.services.auto_scanner_service.log_scanner_event")
@patch("apps.trading.services.auto_scanner_service.BinanceService")
def test_admin_top_mover_removal_mirrors_to_regular_users(mock_binance_cls, mock_log):
    admin = get_user_model().objects.create_user(
        "sync-remove-admin@example.com", password="secure-pass", is_staff=True
    )
    regular = get_user_model().objects.create_user("sync-remove-regular@example.com", password="secure-pass")
    mock_binance_cls.return_value.fetch_klines.return_value = _candles()
    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("BTCUSDT")
    sync_top_movers_to_scanner(admin, top_n=1, quote_asset="USDT")
    assert TradingBotConfig.objects.filter(user=regular, symbol="BTCUSDT").exists()

    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("ETHUSDT")
    sync_top_movers_to_scanner(admin, top_n=1, quote_asset="USDT")

    assert not TradingBotConfig.objects.filter(user=regular, symbol="BTCUSDT").exists()
    assert TradingBotConfig.objects.filter(user=regular, symbol="ETHUSDT").exists()
