import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.models import TradingBotConfig


@pytest.mark.django_db
def test_config_api_lists_and_adds_multiple_scanner_coins():
    user = get_user_model().objects.create_user(
        "scanner@example.com",
        password="secure-pass",
    )
    source = TradingBotConfig.objects.create(
        user=user,
        symbol="BTCUSDT",
        leverage=25,
        timeframe_signal="5m",
        is_running=True,
    )
    client = APIClient()
    client.force_authenticate(user)

    created = client.post(
        "/api/bot/config",
        {
            "symbol": "ethusdt",
            "copy_from_symbol": source.symbol,
            "start_scanning": True,
        },
        format="json",
    )

    assert created.status_code == 201
    assert created.data["symbol"] == "ETHUSDT"
    assert created.data["leverage"] == 25
    assert created.data["timeframe_signal"] == "5m"
    assert created.data["is_running"] is True

    response = client.get("/api/bot/config")
    assert response.status_code == 200
    assert [item["symbol"] for item in response.data] == ["BTCUSDT", "ETHUSDT"]


@pytest.mark.django_db
def test_config_api_accepts_one_character_base_symbol():
    user = get_user_model().objects.create_user(
        "short-symbol@example.com",
        password="secure-pass",
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/bot/config",
        {"symbol": "husdt", "start_scanning": True},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["symbol"] == "HUSDT"
    assert response.data["is_running"] is True


@pytest.mark.django_db
def test_config_api_removes_only_requested_coin():
    user = get_user_model().objects.create_user(
        "remove-scanner@example.com",
        password="secure-pass",
    )
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    TradingBotConfig.objects.create(user=user, symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.delete("/api/bot/config?symbol=ETHUSDT")

    assert response.status_code == 204
    assert list(
        TradingBotConfig.objects.filter(user=user).values_list("symbol", flat=True)
    ) == ["BTCUSDT"]


@pytest.mark.django_db
def test_max_open_positions_is_shared_across_coin_configs():
    user = get_user_model().objects.create_user(
        "position-limit@example.com",
        password="secure-pass",
    )
    btc = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    eth = TradingBotConfig.objects.create(user=user, symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.put(
        "/api/bot/config",
        {"symbol": btc.symbol, "max_open_positions": 7},
        format="json",
    )

    assert response.status_code == 200
    eth.refresh_from_db()
    assert eth.max_open_positions == 7


@pytest.mark.django_db
def test_live_mode_is_shared_across_coin_configs(settings):
    settings.ENABLE_LIVE_TRADING = True
    user = get_user_model().objects.create_user(
        "live-mode@example.com",
        password="secure-pass",
    )
    btc = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    eth = TradingBotConfig.objects.create(user=user, symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.put(
        "/api/bot/config",
        {"symbol": btc.symbol, "live_mode_requested": True},
        format="json",
    )

    assert response.status_code == 200
    eth.refresh_from_db()
    assert eth.live_mode_requested is True


@pytest.mark.django_db
def test_new_scanner_coin_inherits_account_live_mode():
    user = get_user_model().objects.create_user(
        "new-live-coin@example.com",
        password="secure-pass",
    )
    TradingBotConfig.objects.create(
        user=user,
        symbol="BTCUSDT",
        live_mode_requested=True,
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.post(
        "/api/bot/config",
        {"symbol": "ETHUSDT", "start_scanning": True},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["live_mode_requested"] is True
