from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.trading.services.binance_service import BinanceAPIError, BinanceService, SymbolRules


def response(status_code: int, payload: dict) -> Mock:
    result = Mock()
    result.status_code = status_code
    result.is_error = status_code >= 400
    result.reason_phrase = "Unauthorized"
    result.json.return_value = payload
    return result


@override_settings(BINANCE_TESTNET=False)
@patch("apps.trading.services.binance_service.httpx.request")
def test_connection_reports_missing_futures_trade_permission(request):
    request.side_effect = [
        response(200, {"canTrade": True}),
        response(200, {"enableFutures": False, "ipRestrict": True}),
    ]

    result = BinanceService("key", "secret").test_connection()

    assert result["connected"] is True
    assert result["can_trade"] is False
    assert result["futures_enabled"] is False
    assert "Enable Futures trading is disabled" in result["message"]


@patch("apps.trading.services.binance_service.httpx.request")
def test_signed_error_omits_signature_url(request):
    request.return_value = response(
        401,
        {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action"},
    )

    with pytest.raises(BinanceAPIError) as exc_info:
        BinanceService("key", "secret").set_margin_type("BTCUSDT", "isolated")

    assert exc_info.value.code == -2015
    assert "signature=" not in str(exc_info.value)
    assert "Invalid API-key" in str(exc_info.value)


@patch("apps.trading.services.binance_service.httpx.request")
def test_user_trades_chunks_windows_longer_than_seven_days(request):
    """
    /fapi/v1/userTrades rejects a startTime more than 7 days before endTime
    (error -1127). A position held open longer than a week must still get
    its full fill history instead of that single call failing outright —
    this is the bug behind closed-trade PnL not matching Binance's actual
    numbers for any trade that wasn't closed within a week of opening.
    """
    now_ms = 1_700_000_000_000
    start_ms = now_ms - (15 * 24 * 60 * 60 * 1000)  # opened 15 days ago
    request.side_effect = [
        response(200, [{"id": 1, "side": "BUY", "price": "100", "qty": "1", "realizedPnl": "0", "commission": "0.01"}]),
        response(200, [{"id": 2, "side": "SELL", "price": "110", "qty": "1", "realizedPnl": "10", "commission": "0.01"}]),
        response(200, []),
    ]

    with patch("apps.trading.services.binance_service.time.time", return_value=now_ms / 1000):
        fills = BinanceService("key", "secret").user_trades("BTCUSDT", start_ms)

    assert [f["id"] for f in fills] == [1, 2]
    assert request.call_count == 3
    called_windows = [call.args[1].split("?", 1)[1] for call in request.call_args_list]
    for window in called_windows:
        assert "startTime=" in window and "endTime=" in window


def _rules() -> SymbolRules:
    return SymbolRules(
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5"),
    )


def test_normalize_order_rejects_below_min_notional_by_default():
    with pytest.raises(ValueError, match="minimum notional"):
        BinanceService.normalize_order(Decimal("100"), Decimal("0.001"), _rules())


def test_normalize_order_skips_min_notional_check_when_requested():
    """
    Closing an existing position (e.g. the runner leftover after TP1/TP2 fills)
    must not be blocked by the same MIN_NOTIONAL floor that guards new entries —
    otherwise the position gets permanently stuck retrying an unwinnable close.
    """
    price, quantity = BinanceService.normalize_order(
        Decimal("100"), Decimal("0.001"), _rules(), skip_min_notional=True
    )
    assert price == Decimal("100.00")
    assert quantity == Decimal("0.001")

