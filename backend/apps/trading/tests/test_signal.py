from dataclasses import replace

from apps.trading.services.indicator_service import calculate_indicators
from apps.trading.services.signal_service import (
    entry_location_block_reason,
    score_signal,
)
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
    assert signal.long_score >= 85
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


def test_early_uptrend_allows_faster_entry_below_confirmed_threshold():
    indicators = entry_ready_indicators()
    signal = score_signal(
        replace(
            indicators,
            price=101.5,
            ma99=105.0,
            volume=100.0,
            volume_ma20=200.0,
            candles=[
                {"ma7": 98, "ma25": 97, "ma99": 105, "delta": 1, "cvd": 10, "close": 98},
                {"ma7": 99, "ma25": 97.2, "ma99": 105, "delta": -1, "cvd": 11, "close": 99},
                {"ma7": 100, "ma25": 97.4, "ma99": 105, "delta": 1, "cvd": 10, "close": 100},
                {"ma7": 101, "ma25": 97.6, "ma99": 105, "delta": -1, "cvd": 11, "close": 101},
                {"ma7": 102, "ma25": 97.8, "ma99": 105, "delta": 1, "cvd": 10, "close": 102},
            ],
        ),
        trend_state=TrendState.EARLY_UPTREND,
        open_interest_change_percent=0.0,
        funding_rate=0.001,
        top_ratio_direction=0.0,
    )
    assert signal.signal == "LONG"
    assert signal.risk_multiplier == 0.5
    assert signal.long_score == 63


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


def sideway_reversal_candles():
    return [
        {"open": 100, "close": 98, "delta": -1, "cvd": 10, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 98, "close": 96, "delta": -1, "cvd": 9, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 96, "close": 94, "delta": -1, "cvd": 8, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 94, "close": 96, "delta": 1, "cvd": 9, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 96, "close": 99, "delta": 1, "cvd": 11, "ma7": 97, "ma25": 97, "ma99": 96},
    ]


def test_sideway_bullish_reversal_allows_long_entry():
    indicators = entry_ready_indicators()
    signal = score_signal(
        replace(
            indicators,
            price=indicators.ma7 + indicators.atr * 0.1,
            volume=200.0,
            volume_ma20=100.0,
            candles=sideway_reversal_candles(),
        ),
        trend_state=TrendState.SIDEWAY,
        open_interest_change_percent=0.0,
        funding_rate=0.0001,
        top_ratio_direction=0.0,
    )
    assert signal.signal == "LONG"
    assert signal.risk_multiplier == 0.5
    assert "bullish reversal" in signal.reasons[0]


def test_sideway_reversal_pattern_without_volume_confirmation_blocks_entry():
    indicators = entry_ready_indicators()
    signal = score_signal(
        replace(
            indicators,
            price=indicators.ma7 + indicators.atr * 0.1,
            volume=100.0,
            volume_ma20=200.0,
            candles=sideway_reversal_candles(),
        ),
        trend_state=TrendState.SIDEWAY,
        open_interest_change_percent=0.0,
        funding_rate=0.0001,
        top_ratio_direction=0.0,
    )
    assert signal.signal == "NO_TRADE"
    assert signal.reasons == ["trend state is SIDEWAY"]


def test_weak_uptrend_no_longer_allows_new_entry():
    indicators = entry_ready_indicators()
    signal = score_signal(
        indicators,
        trend_state=TrendState.WEAK_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert signal.risk_multiplier == 0.5
    assert signal.long_score == 107
    assert "below the 85 entry threshold" in signal.reasons[0]


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
