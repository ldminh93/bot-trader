from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import Trade
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
    service.client.mark_price.return_value = Decimal("100.00")
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


def test_live_entry_places_trailing_stop_for_tp3_when_configured():
    """
    Reproduces the reported bug: TP3 never appeared on Binance as a trailing
    stop because it was only tracked in bot-side software. When
    tp3_trailing_percent is set, TP3 must be a real TRAILING_STOP_MARKET
    order on the exchange, and the fixed TP1/TP2 orders are unaffected.
    """
    service = service_with_client()
    service.config.tp3_trailing_percent = Decimal("3.00")

    service.place_entry(
        "LONG",
        Decimal("0.100"),
        Decimal("100"),
        Decimal("95.07"),
        (Decimal("105.09"), Decimal("110.09"), Decimal("115.09")),
    )

    assert service.client.place_close_algo_order.call_count == 4
    stop_call, tp1_call, tp2_call, trailing_call = service.client.place_close_algo_order.call_args_list
    assert stop_call.args[2] == "STOP_MARKET"
    assert tp1_call.args[2:4] == ("TAKE_PROFIT_MARKET", Decimal("105.00"))
    assert tp2_call.args[2:4] == ("TAKE_PROFIT_MARKET", Decimal("110.00"))
    assert trailing_call.args[2:4] == ("TRAILING_STOP_MARKET", Decimal("115.00"))
    assert trailing_call.kwargs == {
        "close_position": True,
        "callback_rate": Decimal("3.0"),
    }


def test_live_entry_skips_tp_leg_that_rounds_to_zero_quantity():
    """
    Reproduces the reported bug: a position small enough that TP1/TP2's 30%/40%
    share floors to 0 at the symbol's step size used to submit a doomed
    0-quantity order, which Binance rejects, tripping place_entry's emergency
    full-close of the entire freshly-opened position. The zero legs must be
    skipped instead.
    """
    service = service_with_client()
    service.client.normalize_order.return_value = (Decimal("100.00"), Decimal("0.002"))
    service.client.place_market_order.return_value = {
        "avgPrice": "100.00",
        "executedQty": "0.002",
    }

    service.place_entry(
        "LONG",
        Decimal("0.002"),
        Decimal("100"),
        Decimal("95.07"),
        (Decimal("105.09"), Decimal("110.09"), Decimal("115.09")),
    )

    assert service.client.place_close_algo_order.call_count == 2
    stop_call, tp3_call = service.client.place_close_algo_order.call_args_list
    assert stop_call.args[2] == "STOP_MARKET"
    assert tp3_call.args[2:4] == ("TAKE_PROFIT_MARKET", Decimal("115.00"))
    assert tp3_call.kwargs == {"quantity": Decimal("0.002")}


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


def test_close_position_skips_min_notional_check():
    """
    Reproduces the reported bug: closing the small runner leftover after TP1/TP2
    fills must not raise "Order is below Binance minimum notional" — closing an
    existing position must bypass the check that only guards new entries.
    """
    service = service_with_client()

    service.close_position("LONG", Decimal("0.001"), Decimal("100"))

    service.client.normalize_order.assert_called_once_with(
        Decimal("100"), Decimal("0.001"), service.client.symbol_rules.return_value, skip_min_notional=True
    )
    service.client.place_market_order.assert_called_once_with(
        "BTCUSDT", "SELL", Decimal("0.100"), reduce_only=True
    )


def _open_trade(**overrides) -> Trade:
    user = get_user_model().objects.create_user("live-update@example.com", password="secure-pass")
    defaults = dict(
        user=user,
        symbol="BTCUSDT",
        side=Trade.Side.LONG,
        status=Trade.Status.OPEN,
        entry_price=Decimal("100"),
        quantity=Decimal("1.000"),
        remaining_quantity=Decimal("1.000"),
        leverage=10,
        stop_loss=Decimal("95"),
        initial_stop_loss=Decimal("95"),
        take_profit_1=Decimal("105"),
        take_profit_2=Decimal("110"),
        take_profit_3=Decimal("115"),
        open_reason="test",
        is_paper=False,
    )
    defaults.update(overrides)
    return Trade.objects.create(**defaults)


def _live_service(trade: Trade) -> LiveTradingService:
    service = LiveTradingService.__new__(LiveTradingService)
    service.config = SimpleNamespace(symbol=trade.symbol, margin_type="isolated", leverage=trade.leverage)
    service.client = Mock()
    service.client.position_unrealized_pnl.return_value = Decimal("0")
    return service


@pytest.mark.django_db
def test_update_exchange_sl_replaces_trailing_stop_for_unfired_tp3():
    """
    Reproduces the reported bug: TP3's trailing stop never appeared on
    Binance. Every SL-step update cancels and re-places protective orders;
    the still-open TP3 leg must be re-placed as a TRAILING_STOP_MARKET, not
    silently dropped.
    """
    trade = _open_trade(tp1_hit=True, tp2_hit=True)
    service = _live_service(trade)
    service.client.symbol_rules.return_value = SymbolRules(
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5"),
    )
    service.client.mark_price.return_value = Decimal("100.00")

    service._update_exchange_sl(trade, tp3_trailing_percent=3.0)

    calls = service.client.place_close_algo_order.call_args_list
    assert len(calls) == 2
    sl_call, trailing_call = calls
    assert sl_call.args[2] == "STOP_MARKET"
    assert trailing_call.args[2:4] == ("TRAILING_STOP_MARKET", Decimal("115.00"))
    assert trailing_call.kwargs == {
        "close_position": True,
        "callback_rate": Decimal("3.0"),
    }


@pytest.mark.django_db
def test_update_trade_accrues_tp1_estimate_when_exchange_reports_partial_fill():
    """
    Reproduces the reported bug: a position that hit TP1/TP2/TP3 sometimes
    shows a wrong total profit. Root cause — the live path only recorded
    realized_pnl at the very end via _sync_close_from_fills; if that Binance
    fills lookup ever failed, close_trade()'s own partial-close only covered
    the final remaining slice, silently losing every earlier TP leg's profit.
    This asserts TP1's leg is accrued the moment the exchange reports the
    corresponding quantity drop, using TP1's own target price.
    """
    trade = _open_trade()
    service = _live_service(trade)
    service.client.position_amount.return_value = trade.quantity * Decimal("0.70")

    service.update_trade(trade, current_price=102, atr=0, trailing_multiplier=0)

    assert trade.tp1_hit is True
    assert trade.remaining_quantity == trade.quantity * Decimal("0.70")
    expected_qty = trade.quantity * Decimal("0.30")
    expected_gross = (trade.take_profit_1 - trade.entry_price) * expected_qty
    expected_fee = trade.take_profit_1 * expected_qty * Decimal("0.0005")
    assert trade.realized_pnl == expected_gross - expected_fee


@pytest.mark.django_db
def test_update_trade_final_close_does_not_lose_earlier_tp_legs_when_fills_lookup_fails():
    """
    The core regression: TP1 accrues its estimate, then the position fully
    closes but Binance's fills lookup fails (user_trades raises/returns
    nothing) — realized_pnl must still include TP1's profit, not just the
    final leg's, which was the reported symptom.
    """
    trade = _open_trade()
    service = _live_service(trade)

    service.client.position_amount.return_value = trade.quantity * Decimal("0.70")
    service.update_trade(trade, current_price=102, atr=0, trailing_multiplier=0)
    tp1_accrual = trade.realized_pnl
    assert tp1_accrual > 0

    service.client.position_amount.return_value = Decimal("0")
    service.client.user_trades.side_effect = RuntimeError("Binance API error -1003")

    service.update_trade(trade, current_price=115, atr=0, trailing_multiplier=0)

    assert trade.status == Trade.Status.CLOSED
    final_leg_qty = trade.quantity * Decimal("0.70")
    final_gross = (Decimal("115") - trade.entry_price) * final_leg_qty
    final_fee = Decimal("115") * final_leg_qty * Decimal("0.0005")
    assert trade.realized_pnl == tp1_accrual + final_gross - final_fee


@pytest.mark.django_db
def test_update_trade_final_close_prefers_exact_fills_sum_when_available():
    """When the fills lookup succeeds, its authoritative sum overwrites the
    running estimate — no regression to the already-correct fast path."""
    trade = _open_trade()
    service = _live_service(trade)

    service.client.position_amount.return_value = trade.quantity * Decimal("0.70")
    service.update_trade(trade, current_price=102, atr=0, trailing_multiplier=0)

    service.client.position_amount.return_value = Decimal("0")
    service.client.user_trades.return_value = [
        {"side": "SELL", "price": "105", "qty": "0.300", "realizedPnl": "1.5", "commission": "0.01"},
        {"side": "SELL", "price": "115", "qty": "0.700", "realizedPnl": "10.5", "commission": "0.02"},
        {"side": "BUY", "price": "100", "qty": "1.000", "realizedPnl": "0", "commission": "0.03"},
    ]

    service.update_trade(trade, current_price=115, atr=0, trailing_multiplier=0)

    assert trade.status == Trade.Status.CLOSED
    assert trade.realized_pnl == Decimal("1.5") + Decimal("10.5") - Decimal("0.06")


def test_close_position_skips_order_when_quantity_rounds_to_zero():
    """A remaining quantity that rounds down to zero at step_size has nothing left
    to close on the exchange — must not send a doomed zero-quantity order."""
    service = service_with_client()
    service.client.normalize_order.return_value = (Decimal("100.00"), Decimal("0"))

    result = service.close_position("LONG", Decimal("0.0001"), Decimal("100"))

    assert result is None
    service.client.place_market_order.assert_not_called()


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
