from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import Trade, TradingBotConfig
from apps.trading.services.auto_scanner_service import sync_top_movers_to_scanner


def _movers(*symbols: str) -> dict:
    return {
        "gainers": [{"symbol": s, "price_change_percent": 1.0} for s in symbols],
        "losers": [],
    }


def _open_symbols(user) -> set[str]:
    return set(TradingBotConfig.objects.filter(user=user).values_list("symbol", flat=True))


@pytest.mark.django_db
@patch("apps.trading.services.auto_scanner_service._log")
@patch("apps.trading.services.auto_scanner_service.BinanceService")
def test_sync_replaces_stale_movers_but_keeps_open_positions(mock_binance_cls, mock_log):
    user = get_user_model().objects.create_user("scanner-sync@example.com", password="secure-pass")
    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("BTCUSDT", "ETHUSDT", "SOLUSDT")

    result = sync_top_movers_to_scanner(user, top_n=3, quote_asset="USDT")

    assert set(result["added"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}
    assert result["removed"] == []
    assert _open_symbols(user) == {"BTCUSDT", "ETHUSDT", "SOLUSDT"}

    Trade.objects.create(
        user=user,
        symbol="SOLUSDT",
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

    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("BTCUSDT", "ETHUSDT", "BNBUSDT")
    result = sync_top_movers_to_scanner(user, top_n=3, quote_asset="USDT")

    assert result["added"] == ["BNBUSDT"]
    assert result["removed"] == []
    assert result["skipped"] == ["SOLUSDT"]
    assert _open_symbols(user) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}

    Trade.objects.filter(user=user, symbol="SOLUSDT").update(status=Trade.Status.CLOSED)

    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("ZECUSDT", "VELVETUSDT", "MUSDT")
    result = sync_top_movers_to_scanner(user, top_n=3, quote_asset="USDT")

    assert set(result["added"]) == {"ZECUSDT", "VELVETUSDT", "MUSDT"}
    assert set(result["removed"]) == {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"}
    assert result["skipped"] == []
    assert _open_symbols(user) == {"ZECUSDT", "VELVETUSDT", "MUSDT"}


@pytest.mark.django_db
@patch("apps.trading.services.auto_scanner_service._log")
@patch("apps.trading.services.auto_scanner_service.BinanceService")
def test_sync_does_not_remove_manually_added_config(mock_binance_cls, mock_log):
    user = get_user_model().objects.create_user("scanner-manual@example.com", password="secure-pass")
    TradingBotConfig.objects.create(user=user, symbol="ADAUSDT", is_running=True, auto_registered=False)

    mock_binance_cls.return_value.fetch_top_movers.return_value = _movers("BTCUSDT")
    result = sync_top_movers_to_scanner(user, top_n=1, quote_asset="USDT")

    assert result["added"] == ["BTCUSDT"]
    assert result["removed"] == []
    assert _open_symbols(user) == {"ADAUSDT", "BTCUSDT"}
