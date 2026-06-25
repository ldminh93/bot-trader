from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from apps.trading.services.binance_service import SymbolRules
from apps.trading.services.live_trading_service import (
    ExistingExchangePosition,
    LiveTradingService,
)


def service_with_client() -> LiveTradingService:
    service = LiveTradingService.__new__(LiveTradingService)
    service.config = SimpleNamespace(
        symbol="BTCUSDT",
        margin_type="isolated",
        leverage=10,
    )
    service.client = Mock()
    service.client.symbol_rules.return_value = SymbolRules(
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5"),
    )
    service.client.normalize_order.return_value = (
        Decimal("100.00"),
        Decimal("0.100"),
    )
    service.client.place_market_order.return_value = {
        "avgPrice": "100.00",
        "executedQty": "0.100",
    }
    service.client.position_amount.return_value = Decimal("0")
    return service


def test_live_entry_places_exchange_stop_and_take_profit():
    service = service_with_client()

    service.place_entry(
        "LONG",
        Decimal("0.100"),
        Decimal("100"),
        Decimal("95.07"),
        (Decimal("105.09"), Decimal("110.09"), Decimal("115.09")),
    )

    assert service.client.place_close_algo_order.call_count == 4
    stop_call, tp1_call, tp2_call, tp3_call = service.client.place_close_algo_order.call_args_list
    assert stop_call.args[2:4] == ("STOP_MARKET", Decimal("95.00"))
    assert stop_call.kwargs == {"close_position": True}
    assert tp1_call.args[2:4] == ("TAKE_PROFIT_MARKET", Decimal("105.00"))
    assert tp1_call.kwargs == {"quantity": Decimal("0.030")}
    assert tp2_call.args[2:4] == ("TAKE_PROFIT_MARKET", Decimal("110.00"))
    assert tp2_call.kwargs == {"quantity": Decimal("0.040")}
    assert tp3_call.args[2:4] == ("TAKE_PROFIT_MARKET", Decimal("115.00"))
    assert tp3_call.kwargs == {"quantity": Decimal("0.030")}


def test_live_entry_closes_position_when_protection_fails():
    service = service_with_client()
    service.client.place_close_algo_order.side_effect = RuntimeError("protection failed")

    with pytest.raises(RuntimeError, match="protection failed"):
        service.place_entry(
            "LONG",
            Decimal("0.100"),
            Decimal("100"),
            Decimal("95"),
            (Decimal("105"), Decimal("110"), Decimal("115")),
        )

    service.client.cancel_all_algo_orders.assert_called_once_with("BTCUSDT")
    assert service.client.place_market_order.call_count == 2
    emergency_close = service.client.place_market_order.call_args_list[-1]
    assert emergency_close.args == ("BTCUSDT", "SELL", Decimal("0.100"))
    assert emergency_close.kwargs == {"reduce_only": True}


def test_live_entry_is_skipped_when_exchange_position_exists():
    service = service_with_client()
    service.client.position_amount.return_value = Decimal("0.250")

    with pytest.raises(ExistingExchangePosition, match="already has an open"):
        service.place_entry(
            "LONG",
            Decimal("0.100"),
            Decimal("100"),
            Decimal("95"),
            (Decimal("105"), Decimal("110"), Decimal("115")),
        )

    service.client.set_margin_type.assert_not_called()
    service.client.set_leverage.assert_not_called()
    service.client.place_market_order.assert_not_called()
