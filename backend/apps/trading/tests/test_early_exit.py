from datetime import timedelta, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading.models import Trade
from apps.trading.services.early_exit_service import (
    evaluate_early_exit,
    opposite_entry_has_new_candle_confirmation,
)


def falling_candles(count: int = 150) -> list[dict]:
    now_ms = int(timezone.now().timestamp() * 1000)
    candles = []
    price = 120.0
    for index in range(count):
        close = price - 0.2
        candles.append(
            {
                "timestamp": now_ms - (count - index) * 900_000,
                "close_timestamp": now_ms - (count - index - 1) * 900_000 - 1,
                "open": price,
                "high": price + 0.1,
                "low": close - 0.1,
                "close": close,
                "volume": 1000,
                "taker_buy_volume": 300,
            }
        )
        price = close
    return candles


def rising_candles(count: int = 150) -> list[dict]:
    now_ms = int(timezone.now().timestamp() * 1000)
    candles = []
    price = 80.0
    for index in range(count):
        close = price + 0.2
        candles.append(
            {
                "timestamp": now_ms - (count - index) * 900_000,
                "close_timestamp": now_ms - (count - index - 1) * 900_000 - 1,
                "open": price,
                "high": close + 0.1,
                "low": price - 0.1,
                "close": close,
                "volume": 1000,
                "taker_buy_volume": 700,
            }
        )
        price = close
    return candles


@patch("apps.trading.services.early_exit_service.BinanceService.market_metrics")
@patch("apps.trading.services.early_exit_service.BinanceService.fetch_klines")
def test_long_early_exit_requires_three_conditions(fetch_klines, market_metrics):
    fetch_klines.return_value = falling_candles()
    market_metrics.return_value = {
        "open_interest_change_available": True,
        "open_interest_change_percent": -1.2,
        "funding_rate": 0.0,
    }
    trade = SimpleNamespace(side=Trade.Side.LONG, symbol="BTCUSDT", unrealized_pnl=0)
    config = SimpleNamespace(adx_min=20)

    decision = evaluate_early_exit(trade, config, long_score=10, short_score=20)

    assert decision.should_close is True
    assert len(decision.conditions) >= 3
    assert "15m close is below MA25" in decision.conditions
    assert "last 3 candle deltas are negative" in decision.conditions
    assert "CVD falling for 2+ consecutive candles" in decision.conditions


@patch("apps.trading.services.early_exit_service.BinanceService.market_metrics")
@patch("apps.trading.services.early_exit_service.BinanceService.fetch_klines")
def test_short_early_exit_requires_three_conditions(fetch_klines, market_metrics):
    fetch_klines.return_value = rising_candles()
    market_metrics.return_value = {
        "open_interest_change_available": True,
        "open_interest_change_percent": -1.2,
        "funding_rate": 0.0,
    }
    trade = SimpleNamespace(side=Trade.Side.SHORT, symbol="BTCUSDT", unrealized_pnl=0)
    config = SimpleNamespace(adx_min=20)

    decision = evaluate_early_exit(trade, config, long_score=20, short_score=10)

    assert decision.should_close is True
    assert len(decision.conditions) >= 3
    assert "15m close is above MA25" in decision.conditions
    assert "last 3 candle deltas are positive" in decision.conditions
    assert "CVD rising for 2+ consecutive candles" in decision.conditions


@patch("apps.trading.services.early_exit_service.calculate_indicators")
@patch("apps.trading.services.early_exit_service.BinanceService.market_metrics")
@patch("apps.trading.services.early_exit_service.BinanceService.fetch_klines")
def test_short_early_exit_can_close_on_two_adverse_conditions(
    fetch_klines,
    market_metrics,
    calculate_indicators,
):
    fetch_klines.return_value = rising_candles()
    # ma7/ma25/ma99 all equal (compressed) so detect_trend_state resolves to
    # SIDEWAY here, keeping this test isolated from the trend-flip condition —
    # it's specifically exercising the 2-condition/opposite-score path.
    calculate_indicators.return_value = SimpleNamespace(
        price=101.0,
        ma7=100.0,
        ma25=100.0,
        ma99=100.0,
        atr=1.0,
        atr_ma20=1.0,
        adx=25.0,
        candles=[
            {"delta": -1.0, "cvd": 5.0, "close": 100.0, "ma7": 100.0, "ma25": 100.0, "ma99": 100.0},
            {"delta": 1.0, "cvd": 4.0, "close": 100.0, "ma7": 100.0, "ma25": 100.0, "ma99": 100.0},
            {"delta": -1.0, "cvd": 3.0, "close": 100.0, "ma7": 100.0, "ma25": 100.0, "ma99": 100.0},
            {"delta": -1.0, "cvd": 2.0, "close": 101.0, "ma7": 100.0, "ma25": 100.0, "ma99": 100.0},
        ],
    )
    market_metrics.return_value = {
        "open_interest_change_available": False,
        "open_interest_change_percent": 0.0,
        "funding_rate": 0.0,
    }
    trade = SimpleNamespace(side=Trade.Side.SHORT, symbol="BTCUSDT", unrealized_pnl=0)
    config = SimpleNamespace(adx_min=20, early_exit_min_conditions=2)

    decision = evaluate_early_exit(trade, config, long_score=70, short_score=10)

    assert decision.should_close is True
    assert len(decision.conditions) == 2
    assert "15m close is above MA25" in decision.conditions
    assert "LONG score is at least 70" in decision.conditions


@patch("apps.trading.services.early_exit_service.calculate_indicators")
@patch("apps.trading.services.early_exit_service.BinanceService.market_metrics")
@patch("apps.trading.services.early_exit_service.BinanceService.fetch_klines")
def test_short_early_exit_flags_confirmed_trend_flip(
    fetch_klines,
    market_metrics,
    calculate_indicators,
):
    """A SHORT held while the 15m trend flips to CONFIRMED_UPTREND should be flagged."""
    fetch_klines.return_value = rising_candles()
    candles = [
        {"delta": 1.0, "cvd": 1.0, "close": 105.0, "ma7": 104.0, "ma25": 101.0, "ma99": 95.0},
        {"delta": 1.0, "cvd": 2.0, "close": 106.0, "ma7": 105.0, "ma25": 102.0, "ma99": 96.0},
        {"delta": 1.0, "cvd": 3.0, "close": 107.0, "ma7": 106.0, "ma25": 103.0, "ma99": 97.0},
        {"delta": 1.0, "cvd": 4.0, "close": 108.0, "ma7": 107.0, "ma25": 104.0, "ma99": 98.0},
    ]
    calculate_indicators.return_value = SimpleNamespace(
        price=108.0, ma7=107.0, ma25=104.0, ma99=98.0, atr=1.0, atr_ma20=1.0, adx=25.0,
        candles=candles,
    )
    market_metrics.return_value = {
        "open_interest_change_available": True,
        "open_interest_change_percent": 5.0,
        "open_interest": 1000.0,
        "funding_rate": 0.0,
    }
    trade = SimpleNamespace(side=Trade.Side.SHORT, symbol="BTCUSDT", unrealized_pnl=0)
    config = SimpleNamespace(adx_min=20)

    decision = evaluate_early_exit(trade, config, long_score=10, short_score=10)

    assert decision.should_close is True
    assert "15m trend flipped to confirmed uptrend" in decision.conditions


@patch("apps.trading.services.early_exit_service.BinanceService.market_metrics")
@patch("apps.trading.services.early_exit_service.BinanceService.fetch_klines")
def test_early_exit_waits_for_new_closed_candle_after_entry(fetch_klines, market_metrics):
    candles = rising_candles()
    fetch_klines.return_value = candles
    market_metrics.return_value = {
        "open_interest_change_available": True,
        "open_interest_change_percent": -1.2,
        "funding_rate": 0.0,
    }
    latest_closed_at = max(
        timezone.datetime.fromtimestamp(
            int(candle["close_timestamp"]) / 1000,
            tz=dt_timezone.utc,
        )
        for candle in candles
    )
    trade = SimpleNamespace(
        side=Trade.Side.SHORT,
        symbol="BTCUSDT",
        opened_at=latest_closed_at,
    )
    config = SimpleNamespace(adx_min=20)

    decision = evaluate_early_exit(trade, config, long_score=20, short_score=10)

    assert decision.should_close is False
    assert decision.conditions == []


@pytest.mark.django_db
def test_opposite_entry_waits_for_newly_closed_candle():
    user = get_user_model().objects.create_user(
        "cooldown@example.com",
        password="secure-pass",
    )
    closed_at = timezone.now() - timedelta(minutes=2)
    Trade.objects.create(
        user=user,
        symbol="BTCUSDT",
        side=Trade.Side.LONG,
        status=Trade.Status.CLOSED,
        entry_price=100,
        exit_price=99,
        quantity=1,
        remaining_quantity=0,
        stop_loss=98,
        take_profit_1=102,
        take_profit_2=104,
        take_profit_3=106,
        open_reason="test",
        close_reason="Early exit (3 conditions): test",
        closed_at=closed_at,
    )

    before_confirmation = [
        {"close_timestamp": int((closed_at - timedelta(seconds=1)).timestamp() * 1000)}
    ]
    after_confirmation = [
        {"close_timestamp": int((closed_at + timedelta(minutes=1)).timestamp() * 1000)}
    ]

    assert opposite_entry_has_new_candle_confirmation(
        user,
        "BTCUSDT",
        Trade.Side.SHORT,
        before_confirmation,
    ) is False
    assert opposite_entry_has_new_candle_confirmation(
        user,
        "BTCUSDT",
        Trade.Side.SHORT,
        after_confirmation,
    ) is True
    assert opposite_entry_has_new_candle_confirmation(
        user,
        "BTCUSDT",
        Trade.Side.LONG,
        before_confirmation,
    ) is True
