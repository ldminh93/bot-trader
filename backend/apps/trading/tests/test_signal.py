from dataclasses import replace

from apps.trading.services.indicator_service import calculate_indicators
from apps.trading.services.signal_service import entry_location_block_reason, score_signal
from apps.trading.services.trend_service import TrendState

from .test_indicators import make_candles


def entry_ready_indicators():
    indicators = calculate_indicators(make_candles())
    return replace(
        indicators,
        price=indicators.ma7 + indicators.atr * 0.5,
    )


def test_confirmed_long_score_reaches_entry_threshold():
    indicators = entry_ready_indicators()
    signal = score_signal(
        indicators,
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "LONG"
    assert signal.long_score >= 75
    assert signal.risk_multiplier == 1.0


def test_early_long_uses_half_risk():
    indicators = entry_ready_indicators()
    signal = score_signal(
        indicators,
        trend_state=TrendState.EARLY_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "LONG"
    assert signal.risk_multiplier == 0.5
    assert signal.long_score == 129


def test_sideway_state_blocks_high_score():
    indicators = calculate_indicators(make_candles())
    signal = score_signal(
        indicators,
        trend_state=TrendState.SIDEWAY,
        open_interest_change_percent=1.2,
        funding_rate=0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert signal.risk_multiplier == 0


def test_weak_uptrend_allows_long_with_half_risk():
    indicators = entry_ready_indicators()
    signal = score_signal(
        indicators,
        trend_state=TrendState.WEAK_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "LONG"
    assert signal.risk_multiplier == 0.5
    assert signal.long_score == 107


def test_overextended_long_is_blocked_even_with_high_score():
    indicators = calculate_indicators(make_candles())
    signal = score_signal(
        indicators,
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0001,
        top_ratio_direction=0.04,
    )

    assert signal.signal == "NO_TRADE"
    assert "LONG entry is overextended" in signal.reasons[0]


def test_entry_location_uses_nearest_ma_support():
    reason = entry_location_block_reason(
        "LONG",
        price=110,
        ma7=105,
        ma25=100,
        atr=4,
    )

    assert reason is not None
    assert "1.25 ATR above MA7" in reason
