from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.trading.services.binance_service import BinanceAPIError, BinanceService


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

