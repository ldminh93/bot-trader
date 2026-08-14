from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.models import Trade, TradingBotConfig

FAKE_EVALUATION = SimpleNamespace(
    indicators=SimpleNamespace(atr=1.0, ma7=99.0, ma25=90.0, ma99=80.0),
    metrics={"price": 100.0},
)


def _user_and_client():
    user = get_user_model().objects.create_user("manual-open@example.com", password="secure-pass")
    client = APIClient()
    client.force_authenticate(user)
    return user, client


@pytest.mark.django_db
@patch("apps.trading.views.collect_market_snapshot", return_value=FAKE_EVALUATION)
def test_manual_open_creates_paper_trade_from_config_risk_settings(mock_snapshot):
    """
    The dashboard's manual-open button should reuse the same risk_service math
    the bot uses for its own entries (config's risk_per_trade_percent, leverage,
    ATR-based SL/TP) rather than requiring the user to type numbers in.
    """
    user, client = _user_and_client()
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", is_running=True)

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "LONG"},
        format="json",
    )

    assert response.status_code == 201
    trade = Trade.objects.get(symbol="BTCUSDT")
    assert trade.side == Trade.Side.LONG
    assert trade.is_paper is True
    assert trade.status == Trade.Status.OPEN
    assert trade.open_reason == "Manual entry"
    assert trade.stop_loss == Decimal("98.5")
    assert trade.initial_stop_loss == trade.stop_loss


@pytest.mark.django_db
@patch("apps.trading.views.collect_market_snapshot", return_value=FAKE_EVALUATION)
def test_manual_open_rejected_when_bot_not_running(mock_snapshot):
    """
    A manually opened position only gets managed (stepped SL, TP1/2/3) once the
    next scheduler cycle picks it up, which only happens for is_running configs
    — opening while stopped would create an orphaned, unmanaged position.
    """
    user, client = _user_and_client()
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", is_running=False)

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "LONG"},
        format="json",
    )

    assert response.status_code == 400
    assert not Trade.objects.filter(symbol="BTCUSDT").exists()
    mock_snapshot.assert_not_called()


@pytest.mark.django_db
@patch("apps.trading.views.collect_market_snapshot", return_value=FAKE_EVALUATION)
def test_manual_open_rejected_when_position_already_open(mock_snapshot):
    user, client = _user_and_client()
    config = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", is_running=True)
    Trade.objects.create(
        user=user,
        symbol=config.symbol,
        side=Trade.Side.LONG,
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        leverage=10,
        stop_loss=Decimal("95"),
        initial_stop_loss=Decimal("95"),
        take_profit_1=Decimal("105"),
        take_profit_2=Decimal("110"),
        take_profit_3=Decimal("115"),
        open_reason="existing",
        is_paper=True,
    )

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "SHORT"},
        format="json",
    )

    assert response.status_code == 409
    assert Trade.objects.filter(symbol="BTCUSDT").count() == 1


@pytest.mark.django_db
def test_manual_open_rejected_for_invalid_side():
    user, client = _user_and_client()
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", is_running=True)

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "UP"},
        format="json",
    )

    assert response.status_code == 400
    assert not Trade.objects.filter(symbol="BTCUSDT").exists()


@pytest.mark.django_db
@patch("apps.trading.views.collect_market_snapshot", return_value=FAKE_EVALUATION)
def test_manual_open_falls_back_to_flat_percent_stop_when_no_ma_support(mock_snapshot):
    """
    Reproduces the reported bug: a SHORT has no resistance above price in this
    evaluation (all MAs are below price), so the MA-anchored stop the bot uses
    for its own entries has no anchor — that's a sane reason to reject an
    *autonomous* entry, but blocking a manual one the same way means the human
    who explicitly chose to trade can never override it. Must fall back to a
    flat stop at the config's own max_margin_loss_percent instead of rejecting.
    """
    user, client = _user_and_client()
    TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", is_running=True)

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "SHORT"},
        format="json",
    )

    assert response.status_code == 201
    trade = Trade.objects.get(symbol="BTCUSDT")
    assert trade.side == Trade.Side.SHORT
    # forced_stop_loss_percent = max_margin_loss_percent (20, default) / leverage (10, default) = 2% price move
    assert trade.stop_loss == Decimal("102")


@pytest.mark.django_db
@patch("apps.trading.views.collect_market_snapshot", return_value=FAKE_EVALUATION)
def test_manual_open_rejected_when_no_ma_support_and_no_fallback_available(mock_snapshot):
    """With max_margin_loss_percent disabled (0), there's no configured flat-%
    distance to fall back to — the original MA-support error must surface."""
    user, client = _user_and_client()
    TradingBotConfig.objects.create(
        user=user, symbol="BTCUSDT", is_running=True, max_margin_loss_percent=0,
    )

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "SHORT"},
        format="json",
    )

    assert response.status_code == 400
    assert "resistance" in response.data["detail"]
    assert not Trade.objects.filter(symbol="BTCUSDT").exists()


@pytest.mark.django_db
@patch("apps.trading.views.collect_market_snapshot", return_value=FAKE_EVALUATION)
@patch("apps.trading.views.LiveTradingService")
def test_manual_open_places_live_order_and_creates_trade(mock_live_cls, mock_snapshot, settings):
    settings.ENABLE_LIVE_TRADING = True
    user, client = _user_and_client()
    TradingBotConfig.objects.create(
        user=user, symbol="BTCUSDT", is_running=True, live_mode_requested=True,
    )
    live_instance = mock_live_cls.return_value
    live_instance.client.position_amount.return_value = Decimal("0")
    live_instance.client.account_balance.return_value = 10000.0
    live_instance.place_entry.return_value = {"avgPrice": "100.00", "executedQty": "66.000"}

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "LONG"},
        format="json",
    )

    assert response.status_code == 201
    live_instance.place_entry.assert_called_once()
    trade = Trade.objects.get(symbol="BTCUSDT")
    assert trade.is_paper is False
    assert trade.entry_price == Decimal("100.00")
    assert trade.quantity == Decimal("66.000")


@pytest.mark.django_db
@patch("apps.trading.views.collect_market_snapshot", return_value=FAKE_EVALUATION)
@patch("apps.trading.views.LiveTradingService")
def test_manual_open_rejected_when_live_position_already_exists_on_exchange(mock_live_cls, mock_snapshot, settings):
    settings.ENABLE_LIVE_TRADING = True
    user, client = _user_and_client()
    TradingBotConfig.objects.create(
        user=user, symbol="BTCUSDT", is_running=True, live_mode_requested=True,
    )
    live_instance = mock_live_cls.return_value
    live_instance.client.position_amount.return_value = Decimal("0.5")

    response = client.post(
        "/api/bot/open-position",
        {"symbol": "BTCUSDT", "side": "LONG"},
        format="json",
    )

    assert response.status_code == 409
    live_instance.place_entry.assert_not_called()
    assert not Trade.objects.filter(symbol="BTCUSDT").exists()
