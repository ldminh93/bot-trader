import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.models import CoinCatalog, Trade, TradingBotConfig


def _admin(email: str):
    return get_user_model().objects.create_user(email, password="secure-pass", is_staff=True)


@pytest.mark.django_db
def test_config_api_lists_and_adds_multiple_scanner_coins():
    admin = _admin("scanner@example.com")
    source = TradingBotConfig.objects.create(
        user=admin,
        symbol="BTCUSDT",
        leverage=25,
        timeframe_signal="5m",
        is_running=True,
    )
    CoinCatalog.objects.create(symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(admin)

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
def test_config_api_adds_new_coin_paused_by_default():
    admin = _admin("paused-default@example.com")
    source = TradingBotConfig.objects.create(
        user=admin,
        symbol="BTCUSDT",
        leverage=25,
        timeframe_signal="5m",
        is_running=True,
    )
    CoinCatalog.objects.create(symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(admin)

    created = client.post(
        "/api/bot/config",
        {
            "symbol": "ethusdt",
            "copy_from_symbol": source.symbol,
        },
        format="json",
    )

    assert created.status_code == 201
    assert created.data["symbol"] == "ETHUSDT"
    assert created.data["is_running"] is False


@pytest.mark.django_db
def test_config_api_accepts_one_character_base_symbol():
    admin = _admin("short-symbol@example.com")
    CoinCatalog.objects.create(symbol="HUSDT")
    client = APIClient()
    client.force_authenticate(admin)

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
    admin = _admin("remove-scanner@example.com")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT")
    TradingBotConfig.objects.create(user=admin, symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.delete("/api/bot/config?symbol=ETHUSDT")

    assert response.status_code == 204
    assert list(
        TradingBotConfig.objects.filter(user=admin).values_list("symbol", flat=True)
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
def test_account_wide_strategy_fields_are_shared_across_coin_configs():
    """
    position_margin_usdt, confidence_leverage_enabled, min_effective_leverage,
    auto_suppress_losing_tags, and auto_suppress_losing_symbols are account-wide
    (TradingBotConfig.ACCOUNT_WIDE_FIELDS): saving any of them on one coin must
    propagate to every other coin, same as max_open_positions/live_mode_requested.
    """
    user = get_user_model().objects.create_user(
        "shared-strategy@example.com",
        password="secure-pass",
    )
    btc = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    eth = TradingBotConfig.objects.create(user=user, symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.put(
        "/api/bot/config",
        {
            "symbol": btc.symbol,
            "position_margin_usdt": "75",
            "confidence_leverage_enabled": False,
            "min_effective_leverage": 5,
            "auto_suppress_losing_tags": False,
            "auto_suppress_losing_symbols": True,
        },
        format="json",
    )

    assert response.status_code == 200
    eth.refresh_from_db()
    assert eth.position_margin_usdt == 75
    assert eth.confidence_leverage_enabled is False
    assert eth.min_effective_leverage == 5
    assert eth.auto_suppress_losing_tags is False
    assert eth.auto_suppress_losing_symbols is True


@pytest.mark.django_db
def test_new_coin_inherits_account_wide_strategy_fields_without_explicit_copy():
    """
    Adding a coin without copy_from_symbol must still pick up the account's
    current shared value for the account-wide fields, since they're no longer
    meant to vary per coin.
    """
    admin = _admin("new-coin-inherits@example.com")
    TradingBotConfig.objects.create(
        user=admin,
        symbol="BTCUSDT",
        position_margin_usdt=60,
        auto_suppress_losing_tags=False,
    )
    CoinCatalog.objects.create(symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(
        "/api/bot/config",
        {"symbol": "ethusdt"},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["position_margin_usdt"] == "60.00000000"
    assert response.data["auto_suppress_losing_tags"] is False


@pytest.mark.django_db
def test_pause_all_stops_every_running_coin():
    user = get_user_model().objects.create_user("pause-all@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", is_running=True)
    TradingBotConfig.objects.create(user=user, symbol="ETHUSDT", is_running=True)
    TradingBotConfig.objects.create(user=user, symbol="SOLUSDT", is_running=False)
    client = APIClient()
    client.force_authenticate(user)

    response = client.post("/api/bot/config/pause-all")

    assert response.status_code == 200
    assert set(response.data["paused"]) == {"BTCUSDT", "ETHUSDT"}
    assert not TradingBotConfig.objects.filter(user=user, is_running=True).exists()


@pytest.mark.django_db
def test_scan_all_starts_every_paused_coin():
    user = get_user_model().objects.create_user("scan-all@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", is_running=False)
    TradingBotConfig.objects.create(user=user, symbol="ETHUSDT", is_running=True)
    client = APIClient()
    client.force_authenticate(user)

    response = client.post("/api/bot/config/scan-all")

    assert response.status_code == 200
    assert response.data["started"] == ["BTCUSDT"]
    assert not TradingBotConfig.objects.filter(user=user, is_running=False).exists()


@pytest.mark.django_db
def test_remove_all_deletes_configs_but_keeps_open_positions():
    admin = _admin("remove-all@example.com")
    TradingBotConfig.objects.create(user=admin, symbol="BTCUSDT")
    TradingBotConfig.objects.create(user=admin, symbol="ETHUSDT")
    Trade.objects.create(
        user=admin,
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
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post("/api/bot/config/remove-all")

    assert response.status_code == 200
    assert response.data["removed"] == ["BTCUSDT"]
    assert response.data["skipped"] == ["ETHUSDT"]
    assert list(
        TradingBotConfig.objects.filter(user=admin).values_list("symbol", flat=True)
    ) == ["ETHUSDT"]


@pytest.mark.django_db
def test_config_api_updates_margin_loss_cap():
    user = get_user_model().objects.create_user(
        "margin-cap@example.com",
        password="secure-pass",
    )
    btc = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.put(
        "/api/bot/config",
        {"symbol": btc.symbol, "max_margin_loss_percent": "25.5"},
        format="json",
    )

    assert response.status_code == 200
    btc.refresh_from_db()
    assert str(btc.max_margin_loss_percent) == "25.50"


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
def test_saving_unrelated_field_does_not_reset_live_mode_on_other_coins(settings):
    """
    Reproduces the actual bug: the settings UI always PUTs the full config
    object, not just the edited field, so `live_mode_requested` is present
    on every save even when unchanged. Before this fix, that unconditionally
    re-propagated whatever value the edited coin currently held onto every
    other coin — silently flipping live trading off elsewhere just because
    an unrelated field (leverage) was saved for one coin.
    """
    settings.ENABLE_LIVE_TRADING = True
    user = get_user_model().objects.create_user(
        "no-accidental-live-reset@example.com",
        password="secure-pass",
    )
    btc = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", live_mode_requested=False)
    eth = TradingBotConfig.objects.create(user=user, symbol="ETHUSDT", live_mode_requested=True)
    client = APIClient()
    client.force_authenticate(user)

    response = client.put(
        "/api/bot/config",
        {"symbol": btc.symbol, "live_mode_requested": False, "leverage": 15},
        format="json",
    )

    assert response.status_code == 200
    eth.refresh_from_db()
    assert eth.live_mode_requested is True


@pytest.mark.django_db
def test_saving_unrelated_field_does_not_reset_max_open_positions_on_other_coins():
    """Same bug, for the other account-wide field."""
    user = get_user_model().objects.create_user(
        "no-accidental-position-reset@example.com",
        password="secure-pass",
    )
    btc = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", max_open_positions=5)
    eth = TradingBotConfig.objects.create(user=user, symbol="ETHUSDT", max_open_positions=9)
    client = APIClient()
    client.force_authenticate(user)

    response = client.put(
        "/api/bot/config",
        {"symbol": btc.symbol, "max_open_positions": 5, "leverage": 15},
        format="json",
    )

    assert response.status_code == 200
    eth.refresh_from_db()
    assert eth.max_open_positions == 9


@pytest.mark.django_db
def test_regular_user_cannot_add_coin_at_all():
    """Coin membership is admin-only now — mirrored onto regular users by
    coin_mirror_service, never self-serviced — regardless of catalog state."""
    user = get_user_model().objects.create_user("no-add@example.com", password="secure-pass")
    client = APIClient()
    client.force_authenticate(user)

    without_catalog = client.post("/api/bot/config", {"symbol": "ETHUSDT"}, format="json")
    assert without_catalog.status_code == 403

    CoinCatalog.objects.create(symbol="ETHUSDT")
    with_catalog = client.post("/api/bot/config", {"symbol": "ETHUSDT"}, format="json")
    assert with_catalog.status_code == 403
    assert not TradingBotConfig.objects.filter(user=user, symbol="ETHUSDT").exists()


@pytest.mark.django_db
def test_regular_user_cannot_delete_own_coin():
    user = get_user_model().objects.create_user("no-delete@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.delete("/api/bot/config?symbol=BTCUSDT")

    assert response.status_code == 403
    assert TradingBotConfig.objects.filter(user=user, symbol="BTCUSDT").exists()


@pytest.mark.django_db
def test_regular_user_cannot_remove_all():
    user = get_user_model().objects.create_user("no-remove-all@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post("/api/bot/config/remove-all")

    assert response.status_code == 403
    assert TradingBotConfig.objects.filter(user=user, symbol="BTCUSDT").exists()


@pytest.mark.django_db
def test_regular_user_cannot_add_symbol_to_catalog():
    user = get_user_model().objects.create_user("regular-catalog@example.com", password="secure-pass")
    client = APIClient()
    client.force_authenticate(user)

    response = client.post("/api/coin-catalog", {"symbol": "ETHUSDT"}, format="json")

    assert response.status_code == 403
    assert not CoinCatalog.objects.filter(symbol="ETHUSDT").exists()


@pytest.mark.django_db
def test_admin_can_add_symbol_to_catalog():
    admin = _admin("catalog-admin@example.com")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post("/api/coin-catalog", {"symbol": "ethusdt"}, format="json")

    assert response.status_code == 201
    assert CoinCatalog.objects.filter(symbol="ETHUSDT").exists()


@pytest.mark.django_db
def test_put_start_stop_do_not_silently_create_uncatalogued_coin():
    user = get_user_model().objects.create_user("no-upsert@example.com", password="secure-pass")
    client = APIClient()
    client.force_authenticate(user)

    put_response = client.put("/api/bot/config", {"symbol": "ETHUSDT", "leverage": 5}, format="json")
    start_response = client.post("/api/bot/start", {"symbol": "ETHUSDT"}, format="json")
    stop_response = client.post("/api/bot/stop", {"symbol": "ETHUSDT"}, format="json")

    assert put_response.status_code == 404
    assert start_response.status_code == 404
    assert stop_response.status_code == 404
    assert not TradingBotConfig.objects.filter(user=user, symbol="ETHUSDT").exists()


@pytest.mark.django_db
def test_new_scanner_coin_inherits_account_live_mode():
    admin = _admin("new-live-coin@example.com")
    TradingBotConfig.objects.create(
        user=admin,
        symbol="BTCUSDT",
        live_mode_requested=True,
    )
    CoinCatalog.objects.create(symbol="ETHUSDT")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.post(
        "/api/bot/config",
        {"symbol": "ETHUSDT", "start_scanning": True},
        format="json",
    )

    assert response.status_code == 201
    assert response.data["live_mode_requested"] is True
