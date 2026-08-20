from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.trading.models import TradingBotConfig
from apps.trading.services.indicator_service import calculate_indicators
from apps.trading.services.market_snapshot_service import evaluate_market_conditions
from apps.trading.services.signal_service import SignalResult
from apps.trading.services.trend_service import TrendState

from .test_indicators import make_candles


def _config(**overrides):
    user = get_user_model().objects.create_user(
        username=f"sideway-gate-{TradingBotConfig.objects.count()}", password="pw"
    )
    defaults = dict(
        symbol="TESTUSDT",
        require_trend_alignment=True,
        require_confirmed_higher_tf=False,
        require_open_interest_confirmation=False,
        require_volume_confirmation=False,
        require_ma7_slope_confirmation=False,
        require_funding_confirmation=False,
    )
    defaults.update(overrides)
    return TradingBotConfig.objects.create(user=user, **defaults)


def _evaluate(config):
    """
    Run evaluate_market_conditions with detect_trend_state/score_signal stubbed
    to simulate a SHORT produced via the pullback-recovery path while the
    current signal-timeframe trend state is SIDEWAY (the exact shape of the
    losing trades this gate targets) — crafting real candles that make
    detect_trend_state/score_signal land on that path naturally is brittle,
    so the trend/signal classification itself is stubbed and only the gate
    logic in evaluate_market_conditions is under test.
    """
    indicators = calculate_indicators(make_candles(direction=-1.0))
    stub_signal = SignalResult(
        signal="SHORT",
        long_score=0,
        short_score=60,
        reasons=["stubbed sideway pullback-recovery SHORT"],
        trend_state="SIDEWAY",
        risk_multiplier=0.5,
    )
    metrics = {
        "open_interest_change_percent": 0.0,
        "open_interest_change_available": True,
        "funding_rate": 0.0002,
        "top_ratio_direction": -0.04,
        "price": 100.0,
    }
    with (
        patch(
            "apps.trading.services.market_snapshot_service.calculate_indicators",
            return_value=indicators,
        ),
        patch(
            "apps.trading.services.market_snapshot_service.detect_trend_state",
            side_effect=[TrendState.SIDEWAY, TrendState.CONFIRMED_DOWNTREND],
        ),
        patch(
            "apps.trading.services.market_snapshot_service.score_signal",
            return_value=stub_signal,
        ),
        patch(
            "apps.trading.services.market_snapshot_service.explain_trend_state",
            return_value=[],
        ),
    ):
        _, signal, *_ = evaluate_market_conditions(
            config, [], [], metrics, oi_series=[1.0, 2.0],
        )
    return signal


class SidewayEntryGateTests(TestCase):
    def test_blocks_entry_while_trend_state_is_sideway(self):
        config = _config(block_sideway_entries=True)
        signal = _evaluate(config)
        self.assertEqual(signal.signal, "NO_TRADE")
        self.assertTrue(any("SIDEWAY" in reason for reason in signal.reasons))

    def test_allows_entry_when_sideway_block_disabled(self):
        config = _config(block_sideway_entries=False)
        signal = _evaluate(config)
        self.assertEqual(signal.signal, "SHORT")
