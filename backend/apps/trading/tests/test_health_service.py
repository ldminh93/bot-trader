from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import Trade, TradingBotConfig, UserBinanceCredential
from apps.trading.services.credential_service import encrypt_secret
from apps.trading.services.health_service import build_live_sync_health


def _live_trade(user, config, **overrides) -> Trade:
    defaults = dict(
        user=user,
        symbol=config.symbol,
        side=Trade.Side.LONG,
        status=Trade.Status.OPEN,
        is_paper=False,
        entry_price=Decimal("100"),
        quantity=Decimal("1"),
        remaining_quantity=Decimal("1"),
        leverage=10,
        stop_loss=Decimal("90"),
        take_profit_1=Decimal("105"),
        take_profit_2=Decimal("110"),
        take_profit_3=Decimal("115"),
        open_reason="test",
    )
    defaults.update(overrides)
    return Trade.objects.create(**defaults)


@pytest.mark.django_db
def test_live_sync_health_auto_closes_trade_already_flat_on_exchange(settings):
    """
    Reproduces the reported bug: the dashboard kept showing a live position as
    open long after Binance had already closed it (SL/TP fill, manual close on
    Binance, or liquidation) because nothing reconciled the local Trade against
    the exchange outside the bot's own 20s cycle, and that cycle only runs for
    configs with is_running=True. Live sync health must self-heal the stale
    Trade instead of only reporting the mismatch.
    """
    settings.ENABLE_LIVE_TRADING = True
    user = get_user_model().objects.create_user(
        "ghost-position@example.com", password="secure-pass"
    )
    UserBinanceCredential.objects.create(
        user=user,
        api_key="key",
        api_secret_encrypted=encrypt_secret("secret"),
        is_active=True,
    )
    config = TradingBotConfig.objects.create(
        user=user, symbol="BTCUSDT", live_mode_requested=True, is_running=False
    )
    trade = _live_trade(user, config)

    fake_client = Mock()
    fake_client.position_amount.return_value = Decimal("0")
    fake_client.mark_price.return_value = Decimal("101")

    with patch(
        "apps.trading.services.health_service.BinanceService", return_value=fake_client
    ), patch(
        "apps.trading.services.live_trading_service.BinanceService", return_value=fake_client
    ), patch(
        "apps.trading.services.health_service.broadcast_user_update"
    ):
        result = build_live_sync_health(user)

    trade.refresh_from_db()
    assert trade.status == Trade.Status.CLOSED
    assert trade.close_reason == "Live position closed by exchange protective order"
    assert result["healed"] == 1
    assert result["mismatches"] == 0
    row = next(r for r in result["rows"] if r["symbol"] == "BTCUSDT")
    assert row["status"] == "auto_closed"
    assert row["bot_open"] is False
    assert row["bot_trade_id"] == trade.id


@pytest.mark.django_db
def test_live_sync_health_reports_mismatch_when_auto_close_fails(settings):
    """If the exchange call to close out the stale trade blows up, the trade
    must stay OPEN and be reported as a mismatch rather than silently
    disappearing from the dashboard's Open Positions list."""
    settings.ENABLE_LIVE_TRADING = True
    user = get_user_model().objects.create_user(
        "ghost-position-fail@example.com", password="secure-pass"
    )
    UserBinanceCredential.objects.create(
        user=user,
        api_key="key",
        api_secret_encrypted=encrypt_secret("secret"),
        is_active=True,
    )
    config = TradingBotConfig.objects.create(
        user=user, symbol="ETHUSDT", live_mode_requested=True, is_running=False
    )
    trade = _live_trade(user, config, symbol="ETHUSDT")

    fake_client = Mock()
    fake_client.position_amount.return_value = Decimal("0")
    fake_client.mark_price.return_value = Decimal("101")
    fake_client.cancel_all_algo_orders.side_effect = RuntimeError("network blip")

    with patch(
        "apps.trading.services.health_service.BinanceService", return_value=fake_client
    ), patch(
        "apps.trading.services.live_trading_service.BinanceService", return_value=fake_client
    ):
        result = build_live_sync_health(user)

    trade.refresh_from_db()
    assert trade.status == Trade.Status.OPEN
    assert result["healed"] == 0
    assert result["mismatches"] == 1
    row = next(r for r in result["rows"] if r["symbol"] == "ETHUSDT")
    assert row["status"] == "mismatch"
    assert row["bot_open"] is True
