import pytest

from apps.trading.services.indicator_service import (
    calculate_indicators,
    detect_long_entry_quality,
    detect_ma_stack_reversal,
    detect_short_entry_quality,
)


def make_candles(count: int = 150, direction: float = 1.0) -> list[dict]:
    candles = []
    price = 100.0
    for index in range(count):
        close = price + direction * (0.25 + index * 0.002)
        volume = 1000 + index * 5
        candles.append(
            {
                "timestamp": index,
                "open": price,
                "high": max(price, close) + 0.4,
                "low": min(price, close) - 0.4,
                "close": close,
                "volume": volume,
                "taker_buy_volume": volume * (0.6 if direction > 0 else 0.4),
            }
        )
        price = close
    return candles


def test_indicator_calculation_returns_complete_result():
    result = calculate_indicators(make_candles())
    assert result.ma7 > result.ma25 > result.ma99
    assert result.delta > 0
    assert result.cvd > 0
    assert result.atr > 0
    assert result.volume_ma20 > 0
    assert result.swing_high > result.swing_low


def test_requires_enough_candles():
    with pytest.raises(ValueError):
        calculate_indicators(make_candles(50))


# ── MA7 cross-recovery (shallow pullback that never reaches MA25) ───────────

def test_long_entry_quality_recovers_on_ma7_reclaim_even_far_from_ma25():
    """
    Price dipped below MA7 for a candle, then reclaimed it — MA25 is far away
    so the old MA25-only zone check would reject this, but it's still a valid
    shallow continuation pullback.
    """
    candles = [
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 100.5, "high": 100.6, "low": 99.0, "close": 99.2, "volume": 900, "ma7": 100.0},
        # Reclaims MA7 (100.0) with a plain bullish close, no hammer wick
        {"open": 99.2, "high": 100.6, "low": 99.0, "close": 100.5, "volume": 1000, "ma7": 100.0},
    ]
    eq = detect_long_entry_quality(candles, atr=1.0, ma25=90.0, vol_ma20=1000.0)
    assert eq.has_pullback is True
    assert eq.has_rejection_candle is True


def test_long_entry_quality_stays_blocked_without_ma7_dip_or_ma25_zone():
    """No MA7 dip and MA25 far away → still no valid pullback (regression guard)."""
    candles = [
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.6, "low": 100.9, "close": 101.4, "volume": 1000, "ma7": 100.0},
    ]
    eq = detect_long_entry_quality(candles, atr=1.0, ma25=90.0, vol_ma20=1000.0)
    assert eq.has_pullback is False
    assert eq.has_rejection_candle is False


def test_long_ma7_cross_recovery_requires_red_previous_candle():
    """A green (not red) previous candle should not qualify as the 'decrease' leg."""
    candles = [
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        # Previous candle is GREEN (close > open), even though it's below MA7
        {"open": 99.0, "high": 99.6, "low": 98.9, "close": 99.2, "volume": 900, "ma7": 100.0},
        {"open": 99.2, "high": 100.6, "low": 99.0, "close": 100.5, "volume": 1000, "ma7": 100.0},
    ]
    eq = detect_long_entry_quality(candles, atr=1.0, ma25=90.0, vol_ma20=1000.0)
    assert eq.has_pullback is False
    assert eq.has_rejection_candle is False


def test_long_ma7_cross_recovery_requires_min_ma_gap():
    """MA7 within 3% of MA25 (choppy/sideway) should block the cross-recovery, even
    with a valid red-then-reclaim candle pattern."""
    candles = [
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0, "volume": 900, "ma7": 100.0},
        {"open": 100.5, "high": 100.6, "low": 99.0, "close": 99.2, "volume": 900, "ma7": 100.0},
        {"open": 99.2, "high": 100.6, "low": 99.0, "close": 100.5, "volume": 1000, "ma7": 100.0},
    ]
    # MA25 = 98.5 -> gap vs MA7 (100.0) is ~1.5%, below the 3% minimum
    eq = detect_long_entry_quality(candles, atr=1.0, ma25=98.5, vol_ma20=1000.0)
    assert eq.has_pullback is False
    assert eq.has_rejection_candle is False


# ── MA-stack reversal (early reversal, independent of trend-confirmation gates) ──

def test_ma_stack_reversal_long_fires_on_bottom_ma_reclaim():
    """
    MA7=90 (bottom) < MA25=95 (middle) < MA99=99 (top). Previous candle is red
    and closed on/below the bottom MA (90); current candle reclaimed it and
    sits between bottom and middle. Should fire LONG with those MA values as
    the forced TP targets.
    """
    candles = [
        {"open": 92.0, "high": 92.5, "low": 89.5, "close": 90.0},  # prev: red, close<=90
        {"open": 90.0, "high": 92.5, "low": 89.8, "close": 92.0},  # last: 90 < 92 < 95
    ]
    result = detect_ma_stack_reversal(candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG")
    assert result.detected is True
    assert result.bottom_ma == 90.0
    assert result.middle_ma == 95.0
    assert result.top_ma == 99.0


def test_ma_stack_reversal_long_ignores_which_ma_is_lowest():
    """The bottom/middle/top assignment is by value, not by MA name (MA25 is
    lowest here, not MA7)."""
    candles = [
        {"open": 87.0, "high": 87.5, "low": 84.5, "close": 85.0},  # prev: red, close<=85
        {"open": 85.0, "high": 87.5, "low": 84.8, "close": 87.0},  # last: 85 < 87 < 90
    ]
    result = detect_ma_stack_reversal(candles, ma7=90.0, ma25=85.0, ma99=99.0, direction="LONG")
    assert result.detected is True
    assert result.bottom_ma == 85.0
    assert result.middle_ma == 90.0
    assert result.top_ma == 99.0


def test_ma_stack_reversal_long_blocked_by_green_previous_candle():
    candles = [
        {"open": 89.0, "high": 90.5, "low": 88.5, "close": 90.0},  # prev: green, not red
        {"open": 90.0, "high": 92.5, "low": 89.8, "close": 92.0},
    ]
    result = detect_ma_stack_reversal(candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG")
    assert result.detected is False


def test_ma_stack_reversal_long_blocked_by_small_ma_gap():
    """bottom/middle MAs bunched within 3% → sideways/choppy, don't fire."""
    candles = [
        {"open": 92.0, "high": 92.5, "low": 89.5, "close": 90.0},
        {"open": 90.0, "high": 91.5, "low": 89.8, "close": 91.0},  # between 90 and 91.1
    ]
    result = detect_ma_stack_reversal(candles, ma7=90.0, ma25=91.1, ma99=99.0, direction="LONG")
    assert result.detected is False


def test_ma_stack_reversal_short_fires_on_top_ma_rejection():
    """Mirror: MA7=110 (top) > MA25=105 (middle) > MA99=100 (bottom). Previous
    candle is green and closed on/above the top MA; current candle rejected
    back below it and sits between middle and top."""
    candles = [
        {"open": 108.0, "high": 110.5, "low": 107.5, "close": 110.0},  # prev: green, close>=110
        {"open": 110.0, "high": 110.2, "low": 107.5, "close": 108.0},  # last: 105 < 108 < 110
    ]
    result = detect_ma_stack_reversal(candles, ma7=110.0, ma25=105.0, ma99=100.0, direction="SHORT")
    assert result.detected is True
    assert result.bottom_ma == 100.0
    assert result.middle_ma == 105.0
    assert result.top_ma == 110.0


def test_short_entry_quality_recovers_on_ma7_reclaim_even_far_from_ma25():
    """Mirror of the LONG case: price poked above MA7, then was rejected back below it."""
    candles = [
        {"open": 99.0, "high": 99.2, "low": 98.8, "close": 99.0, "volume": 900, "ma7": 100.0},
        {"open": 99.0, "high": 99.2, "low": 98.8, "close": 99.0, "volume": 900, "ma7": 100.0},
        {"open": 99.0, "high": 99.2, "low": 98.8, "close": 99.0, "volume": 900, "ma7": 100.0},
        {"open": 99.5, "high": 101.0, "low": 99.4, "close": 100.8, "volume": 900, "ma7": 100.0},
        # Rejected back below MA7 (100.0) with a plain bearish close
        {"open": 100.8, "high": 101.0, "low": 99.4, "close": 99.5, "volume": 1000, "ma7": 100.0},
    ]
    eq = detect_short_entry_quality(candles, atr=1.0, ma25=110.0, vol_ma20=1000.0)
    assert eq.has_pullback is True
    assert eq.has_rejection_candle is True
