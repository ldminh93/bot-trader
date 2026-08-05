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
    sits between bottom and middle. Bottom MA (ma7) curves up over the last 5
    candles and the reclaim candle carries 1.5x average volume, so both the
    mandatory slope and volume gates pass. Should fire LONG with those MA
    values as the forced TP targets.
    """
    candles = [
        {"open": 100.0, "high": 100.2, "low": 96.0, "close": 96.5, "volume": 900, "ma7": 87.0},
        {"open": 96.5, "high": 97.0, "low": 93.0, "close": 93.5, "volume": 900, "ma7": 87.8},
        {"open": 93.5, "high": 94.0, "low": 91.0, "close": 91.5, "volume": 900, "ma7": 88.6},
        {"open": 91.5, "high": 92.0, "low": 89.5, "close": 92.0, "volume": 900, "ma7": 89.3},
        {"open": 92.0, "high": 92.5, "low": 89.5, "close": 90.0, "volume": 900, "ma7": 89.8},  # prev: red, close<=90
        {"open": 90.0, "high": 92.5, "low": 89.8, "close": 92.0, "volume": 1500, "ma7": 90.0},  # last: 90 < 92 < 95
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is True
    assert result.bottom_ma == 90.0
    assert result.middle_ma == 95.0
    assert result.top_ma == 99.0


def test_ma_stack_reversal_long_ignores_which_ma_is_lowest():
    """The bottom/middle/top assignment is by value, not by MA name (MA25 is
    lowest here, not MA7), so the slope confirmation must be read from the
    ma25 series."""
    candles = [
        {"open": 95.0, "high": 95.2, "low": 91.0, "close": 91.5, "volume": 900, "ma25": 82.0},
        {"open": 91.5, "high": 92.0, "low": 88.0, "close": 88.5, "volume": 900, "ma25": 82.8},
        {"open": 88.5, "high": 89.0, "low": 86.0, "close": 86.5, "volume": 900, "ma25": 83.6},
        {"open": 86.5, "high": 87.0, "low": 84.5, "close": 87.0, "volume": 900, "ma25": 84.3},
        {"open": 87.0, "high": 87.5, "low": 84.5, "close": 85.0, "volume": 900, "ma25": 84.8},  # prev: red, close<=85
        {"open": 85.0, "high": 87.5, "low": 84.8, "close": 87.0, "volume": 1500, "ma25": 85.0},  # last: 85 < 87 < 90
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=85.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is True
    assert result.bottom_ma == 85.0
    assert result.middle_ma == 90.0
    assert result.top_ma == 99.0


def test_ma_stack_reversal_long_blocked_by_green_previous_candle():
    candles = [
        {"open": 100.0, "high": 100.2, "low": 96.0, "close": 96.5, "volume": 900, "ma7": 87.0},
        {"open": 96.5, "high": 97.0, "low": 93.0, "close": 93.5, "volume": 900, "ma7": 87.8},
        {"open": 93.5, "high": 94.0, "low": 91.0, "close": 91.5, "volume": 900, "ma7": 88.6},
        {"open": 91.5, "high": 92.0, "low": 89.5, "close": 92.0, "volume": 900, "ma7": 89.3},
        {"open": 89.0, "high": 90.5, "low": 88.5, "close": 90.0, "volume": 900, "ma7": 89.8},  # prev: green, not red
        {"open": 90.0, "high": 92.5, "low": 89.8, "close": 92.0, "volume": 1500, "ma7": 90.0},
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is False


def test_ma_stack_reversal_long_blocked_by_small_ma_gap():
    """bottom/middle MAs bunched within 3% → sideways/choppy, don't fire.
    Volume is intentionally ample so the gap gate is what blocks it."""
    candles = [
        {"open": 92.0, "high": 92.5, "low": 89.5, "close": 90.0, "volume": 900},
        {"open": 90.0, "high": 91.5, "low": 89.8, "close": 91.0, "volume": 1500},  # between 90 and 91.1
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=91.1, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is False


def test_ma_stack_reversal_long_blocked_by_falling_knife_reclaim():
    """
    A single green candle reclaiming the bottom MA (90) right off the low of
    a sharp 5-candle drop (low 88.5) should NOT fire — a close of 90.1 is
    only ~1.8% above that low, short of the 2% min-bounce requirement.
    Volume is intentionally ample so the bounce gate is what blocks it.
    """
    candles = [
        {"open": 100.0, "high": 100.2, "low": 95.0, "close": 95.5, "volume": 900},
        {"open": 95.5, "high": 96.0, "low": 93.0, "close": 93.5, "volume": 900},
        {"open": 93.5, "high": 94.0, "low": 91.0, "close": 91.5, "volume": 900},
        {"open": 91.5, "high": 92.0, "low": 89.0, "close": 89.5, "volume": 900},
        {"open": 90.0, "high": 90.2, "low": 88.5, "close": 89.0, "volume": 900},  # prev: red, close<=90, sets the 5-candle low
        {"open": 89.0, "high": 90.3, "low": 88.8, "close": 90.1, "volume": 1500},  # last: barely reclaims 90
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is False


def test_ma_stack_reversal_long_fires_with_sufficient_bounce_off_low():
    """Same shape as the falling-knife case, but the reclaim candle (90.5)
    clears the 5-candle low (88.5) by >=2%, and the bottom MA (ma7) curves up
    over the last 5 candles with ample rejection volume, so the reversal is
    allowed to fire."""
    candles = [
        {"open": 100.0, "high": 100.2, "low": 95.0, "close": 95.5, "volume": 900, "ma7": 87.0},
        {"open": 95.5, "high": 96.0, "low": 93.0, "close": 93.5, "volume": 900, "ma7": 87.8},
        {"open": 93.5, "high": 94.0, "low": 91.0, "close": 91.5, "volume": 900, "ma7": 88.6},
        {"open": 91.5, "high": 92.0, "low": 89.0, "close": 89.5, "volume": 900, "ma7": 89.3},
        {"open": 90.0, "high": 90.2, "low": 88.5, "close": 89.0, "volume": 900, "ma7": 89.8},  # prev: red, close<=90, sets the 5-candle low
        {"open": 89.0, "high": 90.7, "low": 88.8, "close": 90.5, "volume": 1500, "ma7": 90.0},  # last: clears the 88.5 low by >2%
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is True


def test_ma_stack_reversal_long_blocked_when_bottom_ma_still_sloping_down():
    """Even with a valid reclaim + bounce + volume, if the bottom MA (ma7)
    itself is still declining over the last 5 candles, the reversal hasn't
    rolled over yet — don't fire."""
    candles = [
        {"open": 100.0, "high": 100.2, "low": 95.0, "close": 95.5, "volume": 900, "ma7": 93.0},
        {"open": 95.5, "high": 96.0, "low": 93.0, "close": 93.5, "volume": 900, "ma7": 92.0},
        {"open": 93.5, "high": 94.0, "low": 91.0, "close": 91.5, "volume": 900, "ma7": 91.0},
        {"open": 91.5, "high": 92.0, "low": 89.0, "close": 89.5, "volume": 900, "ma7": 90.5},
        {"open": 90.0, "high": 90.2, "low": 88.5, "close": 89.0, "volume": 900, "ma7": 90.2},
        {"open": 89.0, "high": 90.7, "low": 88.8, "close": 90.5, "volume": 1500, "ma7": 90.1},
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is False


def test_ma_stack_reversal_long_blocked_when_slope_data_insufficient():
    """
    Same valid reclaim + bounce + volume as the passing case above, but with
    no per-candle MA history to confirm the bottom MA is actually curving up.
    Missing slope data must block the reversal, not silently pass — otherwise
    a bounce inside an intact downtrend could fire just because the caller
    didn't supply enough MA history.
    """
    candles = [
        {"open": 92.0, "high": 92.5, "low": 89.5, "close": 90.0, "volume": 900},  # prev: red, close<=90
        {"open": 90.0, "high": 92.5, "low": 89.8, "close": 92.0, "volume": 1500},  # last: 90 < 92 < 95
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is False


def test_ma_stack_reversal_long_blocked_by_thin_rejection_volume():
    """Structurally identical to the passing case (valid reclaim, bounce, and
    a bottom MA already curving up), except the reclaim candle's volume is
    below the 1.2x vol_ma20 floor — a thin, low-participation bounce should
    not be treated as a confirmed reversal."""
    candles = [
        {"open": 100.0, "high": 100.2, "low": 96.0, "close": 96.5, "volume": 900, "ma7": 87.0},
        {"open": 96.5, "high": 97.0, "low": 93.0, "close": 93.5, "volume": 900, "ma7": 87.8},
        {"open": 93.5, "high": 94.0, "low": 91.0, "close": 91.5, "volume": 900, "ma7": 88.6},
        {"open": 91.5, "high": 92.0, "low": 89.5, "close": 92.0, "volume": 900, "ma7": 89.3},
        {"open": 92.0, "high": 92.5, "low": 89.5, "close": 90.0, "volume": 900, "ma7": 89.8},
        {"open": 90.0, "high": 92.5, "low": 89.8, "close": 92.0, "volume": 950, "ma7": 90.0},  # thin volume
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=90.0, ma25=95.0, ma99=99.0, direction="LONG", vol_ma20=1000.0
    )
    assert result.detected is False


def test_ma_stack_reversal_short_blocked_when_top_ma_still_sloping_up():
    """Mirror of the LONG case: a valid rejection + bounce + volume off the
    top MA isn't enough if the top MA itself is still rising over the last 5
    candles — it hasn't rolled over into a downturn yet."""
    candles = [
        {"open": 100.0, "high": 105.0, "low": 99.8, "close": 104.5, "volume": 900, "ma7": 107.0},
        {"open": 104.5, "high": 107.0, "low": 104.0, "close": 106.5, "volume": 900, "ma7": 108.0},
        {"open": 106.5, "high": 109.0, "low": 106.0, "close": 108.5, "volume": 900, "ma7": 109.0},
        {"open": 108.5, "high": 111.0, "low": 108.0, "close": 110.5, "volume": 900, "ma7": 109.5},
        {"open": 110.0, "high": 111.5, "low": 109.8, "close": 111.0, "volume": 900, "ma7": 109.8},
        {"open": 111.0, "high": 111.2, "low": 108.2, "close": 109.0, "volume": 1500, "ma7": 109.9},
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=110.0, ma25=105.0, ma99=100.0, direction="SHORT", vol_ma20=1000.0
    )
    assert result.detected is False


def test_ma_stack_reversal_short_fires_when_top_ma_already_curving_down():
    """Same price action as the blocked case above, but the top MA (ma7)
    is already declining over the last 5 candles — the rejection has
    genuinely rolled over, so it's allowed to fire."""
    candles = [
        {"open": 100.0, "high": 105.0, "low": 99.8, "close": 104.5, "volume": 900, "ma7": 112.0},
        {"open": 104.5, "high": 107.0, "low": 104.0, "close": 106.5, "volume": 900, "ma7": 111.5},
        {"open": 106.5, "high": 109.0, "low": 106.0, "close": 108.5, "volume": 900, "ma7": 111.0},
        {"open": 108.5, "high": 111.0, "low": 108.0, "close": 110.5, "volume": 900, "ma7": 110.5},
        {"open": 110.0, "high": 111.5, "low": 109.8, "close": 111.0, "volume": 900, "ma7": 110.2},
        {"open": 111.0, "high": 111.2, "low": 108.2, "close": 109.0, "volume": 1500, "ma7": 109.9},
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=110.0, ma25=105.0, ma99=100.0, direction="SHORT", vol_ma20=1000.0
    )
    assert result.detected is True


def test_ma_stack_reversal_short_fires_on_top_ma_rejection():
    """Mirror: MA7=110 (top) > MA25=105 (middle) > MA99=100 (bottom). Previous
    candle is green and closed on/above the top MA; current candle rejected
    back below it and sits between middle and top. Top MA curves down over
    the last 5 candles with ample rejection volume."""
    candles = [
        {"open": 100.0, "high": 113.0, "low": 99.8, "close": 112.5, "volume": 900, "ma7": 113.0},
        {"open": 112.5, "high": 113.5, "low": 111.5, "close": 112.0, "volume": 900, "ma7": 112.4},
        {"open": 112.0, "high": 112.8, "low": 111.0, "close": 111.5, "volume": 900, "ma7": 111.8},
        {"open": 111.5, "high": 112.0, "low": 110.5, "close": 111.0, "volume": 900, "ma7": 111.2},
        {"open": 108.0, "high": 110.5, "low": 107.5, "close": 110.0, "volume": 900, "ma7": 110.6},  # prev: green, close>=110
        {"open": 110.0, "high": 110.2, "low": 107.5, "close": 108.0, "volume": 1500, "ma7": 110.0},  # last: 105 < 108 < 110
    ]
    result = detect_ma_stack_reversal(
        candles, ma7=110.0, ma25=105.0, ma99=100.0, direction="SHORT", vol_ma20=1000.0
    )
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
