from dataclasses import replace

from apps.trading.services.indicator_service import calculate_indicators
from apps.trading.services.trend_service import (
    TrendState,
    calculate_slope,
    detect_trend_state,
    risk_multiplier_for_state,
    trend_recently_confirmed,
)

from .test_indicators import make_candles


def with_ma_series(result, ma7_values, ma25_values, ma99_values, deltas):
    candles = []
    cvd = 0
    for index in range(10):
        cvd += deltas[index]
        candles.append(
            {
                "ma7": ma7_values[index],
                "ma25": ma25_values[index],
                "ma99": ma99_values[index],
                "delta": deltas[index],
                "cvd": cvd,
                "close": ma7_values[index],
            }
        )
    return replace(
        result,
        candles=candles,
        price=ma7_values[-1] + 1,
        ma7=ma7_values[-1],
        ma25=ma25_values[-1],
        ma99=ma99_values[-1],
        adx=30,
        atr=2,
        atr_ma20=2,
    )


def test_calculate_slope_uses_recent_values():
    assert calculate_slope([1, 2, 3, 4, 5]) > 0
    assert calculate_slope([5, 4, 3, 2, 1]) < 0


def test_detects_early_uptrend_before_ma25_crosses_ma99():
    base = calculate_indicators(make_candles())
    result = with_ma_series(
        base,
        ma7_values=[100, 101, 102, 103, 104, 105, 106, 107, 108, 109],
        ma25_values=[97, 97.5, 98, 98.5, 99, 99.5, 100, 100.5, 101, 102],
        ma99_values=[110] * 10,
        deltas=[10] * 10,
    )
    assert detect_trend_state(result, 20, [1000, 1050]) == TrendState.EARLY_UPTREND


def test_detects_confirmed_uptrend():
    base = calculate_indicators(make_candles())
    result = with_ma_series(
        base,
        ma7_values=[110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
        ma25_values=[105, 106, 107, 108, 109, 110, 111, 112, 113, 114],
        ma99_values=[100, 100.2, 100.4, 100.6, 100.8, 101, 101.2, 101.4, 101.6, 101.8],
        deltas=[10] * 10,
    )
    assert detect_trend_state(result, 20, [1000, 1050]) == TrendState.CONFIRMED_UPTREND


def test_detects_early_downtrend():
    base = calculate_indicators(make_candles(direction=-1))
    result = with_ma_series(
        base,
        ma7_values=[109, 108, 107, 106, 105, 104, 103, 102, 101, 100],
        ma25_values=[112, 111.5, 111, 110.5, 110, 109.5, 109, 108.5, 108, 107],
        ma99_values=[95] * 10,
        deltas=[-10] * 10,
    )
    result = replace(result, price=99)
    assert detect_trend_state(result, 20, [1000, 1050]) == TrendState.EARLY_DOWNTREND


def test_detects_confirmed_downtrend():
    base = calculate_indicators(make_candles(direction=-1))
    result = with_ma_series(
        base,
        ma7_values=[100, 99, 98, 97, 96, 95, 94, 93, 92, 91],
        ma25_values=[105, 104, 103, 102, 101, 100, 99, 98, 97, 96],
        ma99_values=[110, 109.8, 109.6, 109.4, 109.2, 109, 108.8, 108.6, 108.4, 108.2],
        deltas=[-10] * 10,
    )
    result = replace(result, price=90)
    assert detect_trend_state(result, 20, [1000, 1050]) == TrendState.CONFIRMED_DOWNTREND


def test_single_adverse_signal_does_not_downgrade_confirmed_stack():
    # A single noisy candle (last delta flips negative) should NOT be enough
    # to downgrade an otherwise healthy, fully-aligned confirmed uptrend.
    base = calculate_indicators(make_candles())
    result = with_ma_series(
        base,
        ma7_values=[110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
        ma25_values=[105, 106, 107, 108, 109, 110, 111, 112, 113, 114],
        ma99_values=[100, 100.2, 100.4, 100.6, 100.8, 101, 101.2, 101.4, 101.6, 101.8],
        deltas=[10, 10, 10, 10, 10, 10, 10, 10, 10, -10],
    )
    assert detect_trend_state(result, 20, [1000, 1050]) == TrendState.CONFIRMED_UPTREND


def test_two_adverse_signals_turn_confirmed_stack_into_weak_uptrend():
    # Two conflicting signals (last delta negative AND price back below MA25)
    # should downgrade the stack to WEAK_UPTREND.
    base = calculate_indicators(make_candles())
    result = with_ma_series(
        base,
        ma7_values=[110, 111, 112, 113, 114, 115, 116, 117, 118, 119],
        ma25_values=[105, 106, 107, 108, 109, 110, 111, 112, 113, 114],
        ma99_values=[100, 100.2, 100.4, 100.6, 100.8, 101, 101.2, 101.4, 101.6, 101.8],
        deltas=[10, 10, 10, 10, 10, 10, 10, 10, 10, -10],
    )
    result = replace(result, price=113)
    assert detect_trend_state(result, 20, [1000, 1050]) == TrendState.WEAK_UPTREND


def test_adx_below_threshold_is_sideway():
    result = replace(calculate_indicators(make_candles()), adx=10)
    assert detect_trend_state(result, 20, [1000, 1050]) == TrendState.SIDEWAY


def test_risk_multiplier_by_state():
    assert risk_multiplier_for_state(TrendState.EARLY_UPTREND) == 0.5
    assert risk_multiplier_for_state(TrendState.EARLY_DOWNTREND) == 0.5
    assert risk_multiplier_for_state(TrendState.CONFIRMED_UPTREND) == 1.0
    assert risk_multiplier_for_state(TrendState.CONFIRMED_DOWNTREND) == 1.0
    assert risk_multiplier_for_state(TrendState.WEAK_UPTREND) == 0.5


def _row(ma7, ma25, ma99, close):
    return {"ma7": ma7, "ma25": ma25, "ma99": ma99, "close": close}


def test_trend_recently_confirmed_finds_intact_uptrend_before_pullback():
    # Oldest → newest: clean uptrend structure, then a shallow pullback that
    # never crosses MA7 back through MA25 or closes below MA99.
    candles = [
        _row(90, 88, 80, 91),
        _row(92, 89, 81, 93),
        _row(94, 90, 82, 95),
        _row(95, 91, 83, 92),  # pullback begins, still above MA25/MA99
        _row(95, 91, 83, 91.5),  # current bar (excluded from the scan)
    ]
    assert trend_recently_confirmed(candles, "LONG", lookback=10) is True


def test_trend_recently_confirmed_stops_at_invalidation():
    # Bar index 0 looks like a confirmed uptrend, but the intervening bar
    # index 1 closes below MA99 — that invalidation is found first (scanning
    # newest → oldest) and the scan stops there without ever crediting index 0.
    candles = [
        _row(90, 88, 80, 91),   # confirmed uptrend bar (behind the invalidation)
        _row(90, 89, 85, 84),   # invalidation: close (84) at/below MA99 (85)
        _row(90, 89, 85, 88),   # neutral — no cross, but not yet confirmed either
        _row(90, 89, 85, 87),   # current bar (excluded from the scan)
    ]
    assert trend_recently_confirmed(candles, "LONG", lookback=10) is False


def test_trend_recently_confirmed_respects_lookback_window():
    candles = [_row(94, 90, 82, 95)] + [_row(80, 82, 82, 79) for _ in range(5)] + [_row(80, 82, 82, 79)]
    assert trend_recently_confirmed(candles, "LONG", lookback=3) is False


def test_trend_recently_confirmed_mirrors_for_short():
    candles = [
        _row(80, 84, 90, 79),
        _row(78, 83, 89, 77),
        _row(76, 82, 88, 79),  # bounce begins, still below MA25/MA99
        _row(76, 82, 88, 79.5),  # current bar (excluded from the scan)
    ]
    assert trend_recently_confirmed(candles, "SHORT", lookback=10) is True
    assert trend_recently_confirmed(candles, "LONG", lookback=10) is False


def test_trend_recently_confirmed_false_with_insufficient_data():
    assert trend_recently_confirmed([], "LONG") is False
    assert trend_recently_confirmed([_row(1, 1, 1, 1)], "LONG") is False
