from dataclasses import replace

from apps.trading.services.indicator_service import calculate_indicators
from apps.trading.services.signal_service import (
    DEFAULT_ENTRY_SCORE_THRESHOLD,
    entry_location_block_reason,
    score_signal,
)
from apps.trading.services.trend_service import TrendState

from .test_indicators import make_candles


# ── Helpers ───────────────────────────────────────────────────────────────────

def _candle(open_, high, low, close, volume=1000):
    """Build a minimal candle dict for test fixtures."""
    taker_buy = volume * (0.6 if close >= open_ else 0.4)
    return {
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "taker_buy_volume": taker_buy,
        "delta": taker_buy * 2 - volume,
        "cvd": 0, "ma7": 0, "ma25": 0,
    }


def _with_cumulative_cvd(candles: list[dict]) -> list[dict]:
    """Replace the placeholder cvd=0 with a real running total, as production does."""
    running = 0.0
    result = []
    for candle in candles:
        running += candle["delta"]
        result.append({**candle, "cvd": running})
    return result


def _base_indicators():
    """Return indicators derived from a steadily uptrending candle series."""
    return calculate_indicators(make_candles())


def long_pullback_candles(ma25: float = 100.0, atr: float = 1.0) -> list[dict]:
    """
    Candle sequence ending with a bullish hammer rejection at MA25 support.

    Structure: 3 declining bars (pullback into MA25) followed by a hammer
    candle (lower wick ≥ 0.35 of range, bullish close).
    Volumes are low during the pullback and higher on the rejection.
    """
    # Prior uptrend (sustained buying, before the pullback into MA25 begins) —
    # gives the CVD-slope check something realistic to measure "before the
    # pullback" instead of landing entirely inside the pullback window.
    prior_trend = [
        _candle(97.0, 98.2, 96.8, 98.0, volume=900),
        _candle(98.0, 99.2, 97.8, 99.0, volume=900),
        _candle(99.0, 100.2, 98.8, 100.0, volume=900),
        _candle(100.0, 101.2, 99.8, 101.0, volume=900),
    ]
    # Declining bars approaching MA25 from above
    candles = prior_trend + [
        _candle(101.5, 101.7, 101.2, 101.4, volume=700),
        _candle(101.4, 101.5, 100.8, 101.0, volume=650),
        _candle(101.0, 101.1, 100.4, 100.6, volume=600),
        _candle(100.6, 100.7, 100.0, 100.2, volume=580),
        # Hammer: opens at 100.2, dips to 99.7, closes at 100.8
        # Lower wick = (100.2 - 99.7) / (100.9 - 99.7) = 0.5 / 1.2 ≈ 0.42 ≥ 0.35 ✓
        # Bullish close (100.8 > 100.2) ✓
        _candle(100.2, 100.9, 99.7, 100.8, volume=1500),
    ]
    return _with_cumulative_cvd(candles)


def short_pullback_candles(ma25: float = 100.0, atr: float = 1.0) -> list[dict]:
    """
    Candle sequence ending with a bearish shooting-star rejection at MA25 resistance.

    Structure: 3 rising bars (bounce toward MA25) followed by a shooting-star
    candle (upper wick ≥ 0.35 of range, bearish close).
    Volumes are low during the bounce and higher on the rejection.
    """
    # Prior downtrend (sustained selling, before the bounce into MA25 begins) —
    # gives the CVD-slope check something realistic to measure "before the
    # pullback" instead of landing entirely inside the bounce window.
    prior_trend = [
        _candle(103.0, 103.2, 101.8, 102.0, volume=900),
        _candle(102.0, 102.2, 100.8, 101.0, volume=900),
        _candle(101.0, 101.2, 99.8, 100.0, volume=900),
        _candle(100.0, 100.2, 98.8, 99.0, volume=900),
    ]
    # Rising bars bouncing toward MA25 from below
    candles = prior_trend + [
        _candle(98.5, 98.8, 98.3, 98.7, volume=700),
        _candle(98.7, 99.0, 98.5, 98.9, volume=650),
        _candle(98.9, 99.3, 98.7, 99.2, volume=600),
        _candle(99.2, 99.6, 99.0, 99.5, volume=580),
        # Shooting star: opens at 99.5, spikes to 100.4, closes at 99.2
        # Upper wick = (100.4 - 99.5) / (100.4 - 99.0) = 0.9 / 1.4 ≈ 0.64 ≥ 0.35 ✓
        # Bearish close (99.2 < 99.5) ✓
        _candle(99.5, 100.4, 99.0, 99.2, volume=1500),
    ]
    return _with_cumulative_cvd(candles)


def _long_setup_indicators(candles=None):
    """
    Indicators representing a CONFIRMED_UPTREND with price in the MA25 pullback zone
    and a bullish rejection candle.  All hard gates should pass.
    """
    base = _base_indicators()
    ma25 = 100.0
    atr = 1.0
    return replace(
        base,
        price=100.8,       # within 0.8 ATR above MA25 ✓
        ma7=101.5,         # MA7 > MA25 ✓
        ma25=ma25,
        ma99=95.0,         # price > MA99 ✓
        atr=atr,
        atr_ma20=atr,      # ATR ratio = 1.0, inside [0.7, 2.5] ✓
        adx=25.0,          # ADX > 20 ✓
        volume=1000.0,
        volume_ma20=1000.0,
        candles=candles or long_pullback_candles(ma25=ma25, atr=atr),
    )


def _short_setup_indicators(candles=None):
    """
    Indicators representing a CONFIRMED_DOWNTREND with price in the MA25 pullback zone
    and a bearish rejection candle.  All hard gates should pass.
    """
    base = _base_indicators()
    ma25 = 100.0
    atr = 1.0
    return replace(
        base,
        price=99.2,        # within 0.8 ATR below MA25 ✓
        ma7=98.5,          # MA7 < MA25 ✓
        ma25=ma25,
        ma99=105.0,        # price < MA99 ✓
        atr=atr,
        atr_ma20=atr,      # ATR ratio = 1.0 ✓
        adx=25.0,          # ADX > 20 ✓
        volume=1000.0,
        volume_ma20=1000.0,
        candles=candles or short_pullback_candles(ma25=ma25, atr=atr),
    )


# ── Trend-state gate tests ────────────────────────────────────────────────────

def test_confirmed_long_signal_passes_all_gates():
    """CONFIRMED_UPTREND with valid pullback+rejection → LONG at full risk."""
    signal = score_signal(
        _long_setup_indicators(),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,   # negative = shorts paying, favours LONG
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert signal.signal == "LONG"
    assert signal.long_score >= DEFAULT_ENTRY_SCORE_THRESHOLD
    assert signal.risk_multiplier == 1.0


def test_early_long_uses_half_risk():
    """EARLY_UPTREND produces a LONG with reduced (0.5×) position risk."""
    signal = score_signal(
        _long_setup_indicators(),
        trend_state=TrendState.EARLY_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert signal.signal == "LONG"
    assert signal.risk_multiplier == 0.5


def _with_trend_history(candles, ma7=101.5, ma25=100.0, ma99=95.0):
    """Stamp every candle with the given per-bar ma7/ma25/ma99, leaving OHLC untouched."""
    return [{**c, "ma7": ma7, "ma25": ma25, "ma99": ma99} for c in candles]


def test_sideway_state_recovers_long_pullback_when_trend_recently_confirmed():
    """
    SIDEWAY on the live bar (e.g. ADX/ATR cooled during the pullback), but the
    recent candle history shows an intact uptrend (MA7>MA25>MA99, price>MA25)
    that hasn't invalidated — so the pullback+rejection setup should still fire.
    """
    candles = _with_trend_history(long_pullback_candles(ma25=100.0, atr=1.0))
    signal = score_signal(
        _long_setup_indicators(candles=candles),
        trend_state=TrendState.SIDEWAY,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert signal.signal == "LONG"
    assert signal.risk_multiplier == 0.5
    assert any("confirmed within the last" in reason for reason in signal.reasons)


def test_sideway_state_recovers_short_pullback_when_trend_recently_confirmed():
    """Mirror of the LONG recovery case for a SHORT pullback+rejection setup."""
    candles = _with_trend_history(
        short_pullback_candles(ma25=100.0, atr=1.0), ma7=98.5, ma25=100.0, ma99=105.0,
    )
    signal = score_signal(
        _short_setup_indicators(candles=candles),
        trend_state=TrendState.SIDEWAY,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert signal.signal == "SHORT"
    assert signal.risk_multiplier == 0.5
    assert any("confirmed within the last" in reason for reason in signal.reasons)


def test_sideway_state_stays_blocked_when_trend_was_not_recently_confirmed():
    """No recent confirmed trend in the candle history → SIDEWAY still blocks entry."""
    signal = score_signal(
        _long_setup_indicators(),
        trend_state=TrendState.SIDEWAY,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert signal.signal == "NO_TRADE"


def test_confirmed_short_signal_passes_all_gates():
    """CONFIRMED_DOWNTREND with valid pullback+rejection → SHORT at full risk."""
    signal = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,    # positive = longs paying, favours SHORT
        top_ratio_direction=-0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert signal.signal == "SHORT"
    assert signal.short_score >= DEFAULT_ENTRY_SCORE_THRESHOLD
    assert signal.risk_multiplier == 1.0


def test_early_short_uses_half_risk():
    """EARLY_DOWNTREND produces a SHORT with reduced (0.5×) position risk."""
    signal = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.EARLY_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert signal.signal == "SHORT"
    assert signal.risk_multiplier == 0.5


# ── Hard-gate tests ───────────────────────────────────────────────────────────

def test_adx_below_minimum_blocks_entry():
    """ADX below MIN_ADX_FOR_ENTRY → NO_TRADE regardless of other conditions."""
    signal = score_signal(
        replace(_long_setup_indicators(), adx=15.0),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "ADX" in signal.reasons[0]


def test_atr_contracting_blocks_entry():
    """ATR below 70 % of ATR_MA20 → NO_TRADE (dead market)."""
    signal = score_signal(
        replace(_long_setup_indicators(), atr=0.5, atr_ma20=1.0),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "contracting" in signal.reasons[0]


def test_atr_blow_off_blocks_entry():
    """ATR above 250 % of ATR_MA20 → NO_TRADE (excessive volatility)."""
    signal = score_signal(
        replace(_long_setup_indicators(), atr=3.0, atr_ma20=1.0),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "excessive" in signal.reasons[0]


def test_no_pullback_blocks_short_entry():
    """Price far below MA25 (not in pullback zone) → NO_TRADE."""
    # price is always derived from candles[-1]["close"] in production
    # (see IndicatorResult.price), so the last candle must move too.
    candles = short_pullback_candles()
    candles[-1] = _candle(96.0, 96.2, 94.7, 95.0, volume=1500)
    signal = score_signal(
        replace(_short_setup_indicators(), price=95.0, candles=candles),   # 5 ATR below MA25
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "pullback zone" in signal.reasons[0]


def test_no_rejection_candle_blocks_short_entry():
    """Pullback present but last candle is a green doji (no rejection) → NO_TRADE."""
    # Replace last candle with a bullish candle (close > open, minimal upper wick)
    candles = short_pullback_candles()
    candles[-1] = _candle(99.5, 99.7, 99.3, 99.65, volume=1000)  # tiny wick, bullish
    signal = score_signal(
        replace(_short_setup_indicators(), candles=candles),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "rejection candle" in signal.reasons[0]


def test_no_rejection_candle_blocks_long_entry():
    """Pullback present but last candle is bearish (no hammer) → NO_TRADE."""
    candles = long_pullback_candles()
    candles[-1] = _candle(100.5, 100.6, 100.1, 100.2, volume=1000)  # bearish, tiny wick
    signal = score_signal(
        replace(_long_setup_indicators(), candles=candles),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "rejection candle" in signal.reasons[0]


def test_pullback_gate_skipped_when_disabled():
    """pullback_entry_enabled=False falls back to distance-only check."""
    # Price near MA25 but no rejection candle
    candles = long_pullback_candles()
    candles[-1] = _candle(100.5, 100.6, 100.1, 100.2, volume=1000)
    signal = score_signal(
        replace(_long_setup_indicators(), price=100.5, candles=candles),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        pullback_entry_enabled=False,
    )
    # Signal may be LONG or NO_TRADE based on score, but pullback gate is NOT the reason
    assert "pullback zone" not in " ".join(signal.reasons)
    assert "rejection candle" not in " ".join(signal.reasons)


# ── Sideway / weak-trend tests (unchanged behaviour) ─────────────────────────

def test_sideway_state_blocks_entry():
    # _base_indicators() carries a genuinely uptrending candle history, so the
    # pullback-recovery check (trend confirmed recently, not yet invalidated)
    # legitimately fires here and lifts risk_multiplier off zero — but the
    # entry is still blocked (price isn't in this fixture's MA25 zone), so
    # the trade-blocking behaviour itself is unchanged.
    signal = score_signal(
        _base_indicators(),
        trend_state=TrendState.SIDEWAY,
        open_interest_change_percent=1.2,
        funding_rate=0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"


def sideway_reversal_candles():
    return [
        {"open": 100, "close": 98, "delta": -1, "cvd": 10, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 98, "close": 96, "delta": -1, "cvd": 9, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 96, "close": 94, "delta": -1, "cvd": 8, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 94, "close": 96, "delta": 1, "cvd": 9, "ma7": 97, "ma25": 97, "ma99": 96},
        {"open": 96, "close": 99, "delta": 1, "cvd": 11, "ma7": 97, "ma25": 97, "ma99": 96},
    ]


def test_sideway_bullish_reversal_allows_long_entry():
    base = _base_indicators()
    signal = score_signal(
        replace(
            base,
            price=base.ma7 + base.atr * 0.1,
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
    base = _base_indicators()
    signal = score_signal(
        replace(
            base,
            price=base.ma7 + base.atr * 0.1,
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


def test_weak_downtrend_blocks_short_entry():
    signal = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.WEAK_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "weak downtrend" in signal.reasons[0]


def test_unmatched_trend_state_returns_no_trade():
    """WEAK_UPTREND (no explicit handler) falls through to NO_TRADE."""
    signal = score_signal(
        _long_setup_indicators(),
        trend_state=TrendState.WEAK_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert signal.risk_multiplier == 0.5


# ── Score-threshold and OI-acceleration tests ─────────────────────────────────

def test_oi_acceleration_improves_short_score():
    """Accelerating OI contributes to the short score."""
    signal_with_accel = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],  # accelerating
    )
    signal_flat_oi = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        oi_history=[10000.0, 10100.0, 10100.0, 10100.0],  # flat / decelerating
    )
    assert signal_with_accel.short_score >= signal_flat_oi.short_score


def test_positive_funding_improves_short_score():
    """Positive funding rate (longs paying) scores higher for SHORT than neutral."""
    signal_crowded = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0003,    # positive: longs paying
        top_ratio_direction=-0.04,
    )
    signal_neutral = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0004,   # negative: outside SHORT range entirely
        top_ratio_direction=-0.04,
    )
    assert signal_crowded.short_score > signal_neutral.short_score


# ── Entry-location utility test ───────────────────────────────────────────────

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

