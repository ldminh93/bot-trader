from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import Trade, TradingBotConfig
from apps.trading.services.paper_trading_service import PaperTradingService
from apps.trading.services.risk_service import calculate_risk_plan

from .test_indicators import make_candles


@pytest.mark.django_db
@patch("apps.trading.services.paper_trading_service.BinanceService.fetch_klines")
def test_paper_trade_opens_and_closes_with_fees(fetch_klines):
    fetch_klines.return_value = make_candles()
    user = get_user_model().objects.create_user("trader@example.com", password="secure-pass")
    config = TradingBotConfig.objects.create(user=user, symbol="BTCUSDT")
    plan = calculate_risk_plan(
        "LONG",
        100,
        10_000,
        1,
        2,
        104,
        96,
        ma7=99,
        ma25=98,
        ma99=97,
    )
    trade = PaperTradingService.open_trade(user, config, "LONG", 100, plan, "test setup")

    assert trade.status == Trade.Status.OPEN
    assert trade.leverage == 10
    assert trade.fees > 0
    PaperTradingService.close_trade(trade, Decimal("110"), "target")
    trade.refresh_from_db()
    assert trade.status == Trade.Status.CLOSED
    assert trade.realized_pnl > 0
    assert trade.remaining_quantity == 0


@pytest.mark.django_db
def test_tp1_closes_thirty_percent_and_moves_stop():
    user = get_user_model().objects.create_user("risk@example.com", password="secure-pass")
    config = TradingBotConfig.objects.create(user=user, symbol="ZECUSDT")
    plan = SimpleNamespace(
        quantity=10,
        stop_loss=95,
        take_profit_1=105,
        take_profit_2=110,
        take_profit_3=115,
    )
    trade = PaperTradingService.open_trade(user, config, "LONG", 100, plan, "test setup")
    PaperTradingService.update_trade(trade, 105, 2, 1.2)
    trade.refresh_from_db()
    assert trade.tp1_hit is True
    assert trade.breakeven_moved is True
    assert trade.remaining_quantity == Decimal("7")
    assert trade.stop_loss >= trade.entry_price


@pytest.mark.django_db
def test_return_percent_uses_margin_after_fees():
    user = get_user_model().objects.create_user(
        "margin-roi@example.com",
        password="secure-pass",
    )
    config = TradingBotConfig.objects.create(
        user=user,
        symbol="BTCUSDT",
        leverage=10,
    )
    plan = SimpleNamespace(
        quantity=1,
        stop_loss=90,
        take_profit_1=110,
        take_profit_2=120,
        take_profit_3=130,
    )
    trade = PaperTradingService.open_trade(
        user,
        config,
        "LONG",
        100,
        plan,
        "margin ROI test",
    )

    PaperTradingService.update_trade(trade, 101, 1, 0)
    trade.refresh_from_db()

    expected_net_pnl = Decimal("1") - Decimal("0.05")
    expected_margin = Decimal("10")
    assert trade.unrealized_pnl == Decimal("1")
    assert trade.pnl_percent == expected_net_pnl / expected_margin * Decimal("100")
