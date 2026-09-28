from dataclasses import replace

from apps.trading.services.indicator_service import calculate_indicators
from apps.trading.services.signal_service import (
    DEFAULT_ENTRY_SCORE_THRESHOLD,
    entry_location_block_reason,
    extended_move_block_reason,
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


# ── MA-stack reversal (independent of trend-confirmation gates) ─────────────

def test_ma_stack_reversal_long_signal_fires_despite_hostile_trend_state():
    """
    trend_state is CONFIRMED_DOWNTREND and price (92) sits below MA99 (99) —
    both would normally hard-block a LONG (G1/G3) — but the MA-stack reversal
    path is designed to catch the reversal *before* those gates would confirm
    a new trend, so it fires anyway with its own forced SL/TP. The bottom MA
    (ma7) curves up over the last 5 candles and the reclaim candle carries
    1.5x average volume, satisfying the mandatory slope and volume gates.
    """
    base = _base_indicators()
    candles = [
        _candle(97.0, 97.2, 96.0, 96.5, volume=900),
        _candle(96.5, 97.0, 93.0, 93.5, volume=900),
        _candle(93.5, 94.0, 91.0, 91.5, volume=900),
        _candle(91.5, 92.0, 89.5, 92.0, volume=900),
        _candle(92.0, 92.5, 89.5, 90.0, volume=900),  # prev: red, close<=90 (bottom MA)
        _candle(90.0, 92.5, 89.8, 92.0, volume=1500),  # last: 90 < 92 < 95 (between bottom/middle)
    ]
    candles = [
        {**c, "ma7": ma7}
        for c, ma7 in zip(candles, [87.0, 87.8, 88.6, 89.3, 89.8, 90.0])
    ]
    signal_data = replace(
        base,
        price=92.0,
        ma7=90.0,   # bottom
        ma25=95.0,  # middle
        ma99=99.0,  # top -- price (92) is below MA99, which would normally fail G3
        volume_ma20=1000.0,
        candles=candles,
    )
    signal = score_signal(
        signal_data,
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=0.0,
        funding_rate=0.0,
        top_ratio_direction=0.0,
    )
    assert signal.signal == "LONG"
    assert signal.risk_multiplier == 0.5
    assert signal.forced_stop_loss_percent == 10.0
    assert signal.forced_take_profit_1 == 95.0
    assert signal.forced_take_profit_2 == 99.0
    assert "MA stack reversal" in signal.reasons[0]


def test_ma_stack_reversal_disabled_by_enable_long_false():
    base = _base_indicators()
    candles = [
        _candle(92.0, 92.5, 89.5, 90.0),
        _candle(90.0, 92.5, 89.8, 92.0),
    ]
    signal_data = replace(
        base, price=92.0, ma7=90.0, ma25=95.0, ma99=99.0, candles=candles,
    )
    signal = score_signal(
        signal_data,
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=0.0,
        funding_rate=0.0,
        top_ratio_direction=0.0,
        enable_long=False,
    )
    assert signal.signal != "LONG"
    assert signal.forced_stop_loss_percent is None


# ── MA7 cross-recovery (shallow pullback that never reaches MA25) ───────────

def test_long_signal_fires_on_ma7_reclaim_when_ma25_is_far_away():
    """
    Reproduces the chart scenario reported by the user: a CONFIRMED_UPTREND
    where price dips below MA7 and then reclaims it, but MA25 is too far
    away for the old MA25-only zone check to ever pass.  This should no
    longer be blocked by "not in the MA25 pullback zone".
    """
    prior_trend = [
        _candle(97.0, 98.2, 96.8, 98.0, volume=900),
        _candle(98.0, 99.2, 97.8, 99.0, volume=900),
        _candle(99.0, 100.2, 98.8, 100.0, volume=900),
        _candle(100.0, 101.2, 99.8, 101.0, volume=900),
    ]
    candles = prior_trend + [
        _candle(101.0, 101.2, 100.8, 101.0, volume=700),
        _candle(101.0, 101.2, 100.8, 101.0, volume=650),
        _candle(101.0, 101.2, 100.8, 101.0, volume=600),
        _candle(100.5, 100.6, 99.0, 99.2, volume=580),   # dips below MA7 (100.0)
        _candle(99.2, 100.6, 99.0, 100.5, volume=1500),  # reclaims MA7, no hammer wick
    ]
    candles = _with_cumulative_cvd(candles)
    candles = [{**c, "ma7": 100.0} for c in candles]

    signal = score_signal(
        replace(
            _long_setup_indicators(candles=candles),
            price=100.5,
            ma7=100.0,
            ma25=90.0,     # far below price — old MA25-only zone check would reject
        ),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert "pullback zone" not in " ".join(signal.reasons)
    assert "no bullish rejection candle" not in " ".join(signal.reasons)
    assert signal.signal == "LONG"


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


# ── Extended-move gate: unit tests ─────────────────────────────────────────────
#
# Regression coverage for a case the MA-distance gate above misses: after a
# fast dump, price chops sideways near the low while MA7/MA25 catch back down
# to meet it, so "price is in the MA25 pullback zone" no longer means a real
# pullback happened. See specs/001-block-overextended-long for the original
# (MA-distance) gate this one is meant to close the gap on.

def _dump_then_chop_candles() -> list[dict]:
    """21 candles: sharp dump from ~150 to ~99, then 4 candles chopping at the low."""
    dump = [_candle(150 - i, 150 - i - 0.3, 150 - i - 1.5, 150 - i - 1.0, volume=1200) for i in range(17)]
    chop = [
        _candle(99.2, 99.5, 99.0, 99.3, volume=400),
        _candle(99.3, 99.6, 99.1, 99.4, volume=400),
        _candle(99.4, 99.7, 99.2, 99.5, volume=400),
        _candle(99.5, 99.8, 99.3, 99.6, volume=400),
    ]
    return dump + chop


def test_extended_move_blocks_short_after_dump_without_fresh_low():
    """Coin already dumped >10% over the lookback and isn't making a new low → block."""
    candles = _dump_then_chop_candles()
    reason = extended_move_block_reason("SHORT", candles, lookback=20, min_move_pct=0.10)
    assert reason is not None
    assert "already fell" in reason
    assert "fresh low" in reason


def test_extended_move_allows_short_that_makes_a_fresh_low():
    """Same prior dump, but the current candle extends to a new low → not chasing, allow it."""
    candles = _dump_then_chop_candles()
    candles[-1] = _candle(99.5, 99.6, 96.0, 96.5, volume=1200)  # breaks below the chop low
    reason = extended_move_block_reason("SHORT", candles, lookback=20, min_move_pct=0.10)
    assert reason is None


def test_extended_move_ignores_small_moves():
    """A normal, small pullback (< min_move_pct) is never blocked by this gate."""
    candles = short_pullback_candles()
    reason = extended_move_block_reason("SHORT", candles, lookback=20, min_move_pct=0.10)
    assert reason is None  # too few candles for the lookback window in the first place


def test_extended_move_gate_disabled_when_min_pct_is_zero():
    candles = _dump_then_chop_candles()
    reason = extended_move_block_reason("SHORT", candles, lookback=20, min_move_pct=0)
    assert reason is None


# ── Extended-move gate: score_signal integration test ──────────────────────────

def test_score_signal_blocks_short_chasing_a_completed_dump():
    """
    Reproduces the reported case: SHORT would otherwise pass every existing
    gate (CONFIRMED_DOWNTREND, MA7<MA25, price<MA99, MA25 pullback zone,
    bearish rejection candle) but the coin already dumped hard and is just
    chopping near the low without making a fresh low. The extended-move gate
    should block it even though the legacy MA-distance gate would not.
    """
    dump = [_candle(150 - i, 150 - i + 0.3, 150 - i - 1.2, 150 - i - 1.0, volume=1200) for i in range(12)]
    candles = _with_cumulative_cvd(dump) + short_pullback_candles(ma25=100.0, atr=1.0)
    signal = score_signal(
        replace(_short_setup_indicators(), candles=candles),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
    )
    assert signal.signal == "NO_TRADE"
    assert "already fell" in signal.reasons[0]


def test_score_signal_short_unaffected_when_extended_move_gate_disabled():
    """Same setup as above, but with the gate turned off (min_pct=0) → SHORT still fires."""
    dump = [_candle(150 - i, 150 - i + 0.3, 150 - i - 1.2, 150 - i - 1.0, volume=1200) for i in range(12)]
    candles = _with_cumulative_cvd(dump) + short_pullback_candles(ma25=100.0, atr=1.0)
    signal = score_signal(
        replace(_short_setup_indicators(), candles=candles),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        extended_move_min_pct=0,
    )
    assert signal.signal == "SHORT"


# ─────────────────────────────────────────────────────────────────────────────
# SHORT-only tuning: fresh-extreme buffer, SHORT-only lookback override,
# funding "meaningful" threshold, RSI-oversold gate, and asymmetric threshold.
#
# Crypto downtrends mean-revert far more violently than uptrends grind, so
# these give SHORT a stricter bar without touching the LONG path at all.
# Every one of these new score_signal params defaults to "no override" (0 /
# 0.0), so every pre-existing test above keeps passing unchanged.
# ─────────────────────────────────────────────────────────────────────────────

def test_long_signal_unaffected_by_short_only_overrides():
    """
    Regression guard: SHORT-only knobs must have zero effect on a LONG
    evaluation, even set to extreme values that would obviously trip a SHORT
    equivalent. LONG never reads these params, so the result must be
    byte-for-byte identical to not passing them at all.
    """
    baseline = score_signal(
        _long_setup_indicators(),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    with_short_overrides = score_signal(
        _long_setup_indicators(),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
        short_extended_move_lookback_candles=999,
        short_extended_move_fresh_extreme_buffer_pct=5.0,
        short_entry_score_threshold=90,
        short_funding_meaningful_threshold=0.01,
        short_rsi_oversold_max=99.0,
    )
    assert with_short_overrides == baseline
    assert baseline.signal == "LONG"


def test_short_rsi_gate_does_not_affect_long():
    """
    The RSI-oversold gate only exists on the SHORT branch of score_signal —
    a LONG setup with an extremely low (oversold) RSI has no equivalent gate
    to trip and must still fire normally.
    """
    result = score_signal(
        replace(_long_setup_indicators(), rsi=5.0),
        trend_state=TrendState.CONFIRMED_UPTREND,
        open_interest_change_percent=1.2,
        funding_rate=-0.0001,
        top_ratio_direction=0.04,
        oi_history=[10000.0, 10100.0, 10250.0, 10450.0],
    )
    assert result.signal == "LONG"


# ── 1) Extended-move gate: fresh-extreme buffer ───────────────────────────────

def test_extended_move_buffer_blocks_a_marginal_stop_hunt_undercut():
    """
    A 'fresh low' that undercuts the prior low by a fraction of a tick (a
    stop-hunt wick during basing, not the dump actively continuing) is
    allowed with no buffer (old behaviour) but blocked once a buffer is set.
    """
    candles = _dump_then_chop_candles()
    candles[-1] = _candle(99.5, 99.6, 98.99, 99.4, volume=400)  # undercuts prior low (99.0) by ~0.01%

    allowed = extended_move_block_reason("SHORT", candles, lookback=20, min_move_pct=0.10)
    assert allowed is None

    blocked = extended_move_block_reason(
        "SHORT", candles, lookback=20, min_move_pct=0.10, fresh_extreme_buffer_pct=0.005,
    )
    assert blocked is not None
    assert "fresh low" in blocked


def test_extended_move_buffer_still_allows_a_meaningful_fresh_low():
    """A real, meaningful fresh low (well beyond the buffer) is never blocked."""
    candles = _dump_then_chop_candles()
    candles[-1] = _candle(99.5, 99.6, 96.0, 96.5, volume=1200)  # breaks well below the chop low
    reason = extended_move_block_reason(
        "SHORT", candles, lookback=20, min_move_pct=0.10, fresh_extreme_buffer_pct=0.005,
    )
    assert reason is None


# ── 2) Extended-move gate: SHORT-only lookback override ──────────────────────

def _dump_then_long_chop(dump_len: int = 20, chop_len: int = 21) -> list[dict]:
    """
    Sharp dump followed by a long flat chop — long enough that the dump falls
    completely outside a 20-candle lookback (only the flat chop remains
    visible) but is still caught by a 40-candle one.
    """
    dump = [_candle(150 - i, 150 - i - 0.3, 150 - i - 1.5, 150 - i - 1.0, volume=1200) for i in range(dump_len)]
    chop = [
        _candle(99.2 + i * 0.01, 99.5 + i * 0.01, 99.0 + i * 0.01, 99.3 + i * 0.01, volume=400)
        for i in range(chop_len)
    ]
    return dump + chop


def test_extended_move_lookback_override_catches_a_dump_the_default_window_misses():
    """A dump finished more than 20 candles ago is invisible to the shared
    20-candle lookback (the chop alone is too small a move), but a longer
    SHORT-only lookback still sees the completed dump."""
    candles = _dump_then_long_chop()

    within_default_window = extended_move_block_reason("SHORT", candles, lookback=20, min_move_pct=0.10)
    assert within_default_window is None

    within_longer_window = extended_move_block_reason("SHORT", candles, lookback=40, min_move_pct=0.10)
    assert within_longer_window is not None
    assert "already fell" in within_longer_window


def test_score_signal_short_override_lookback_catches_dump_shared_lookback_missed():
    """
    Integration check: with a shared extended_move_lookback_candles too small
    to see the dump, the SHORT-only override still catches it, proving the
    override is actually wired up inside score_signal (not just the standalone
    function).
    """
    dump = [_candle(150 - i, 150 - i + 0.3, 150 - i - 1.2, 150 - i - 1.0, volume=1200) for i in range(12)]
    candles = _with_cumulative_cvd(dump) + short_pullback_candles(ma25=100.0, atr=1.0)

    not_caught = score_signal(
        replace(_short_setup_indicators(), candles=candles),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        extended_move_lookback_candles=5,  # too small: dump falls outside this window
    )
    assert not_caught.signal == "SHORT"

    caught = score_signal(
        replace(_short_setup_indicators(), candles=candles),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        extended_move_lookback_candles=5,
        short_extended_move_lookback_candles=20,
    )
    assert caught.signal == "NO_TRADE"
    assert "already fell" in caught.reasons[0]


# ── 3) Funding rate: "meaningful" threshold for SHORT ─────────────────────────

def test_short_funding_meaningful_threshold_downgrades_marginal_positive_funding():
    """
    A barely-positive funding rate (e.g. +0.02%) is normal baseline funding,
    not a 'crowded long, ripe for a squeeze' signal. With
    short_funding_meaningful_threshold raised, it scores the same as the
    neutral acceptable-range case (+4) instead of the full 'crowded long'
    bonus (+8).
    """
    marginal = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,  # positive, but below the 0.0003 meaningful bar
        top_ratio_direction=-0.04,
    )
    marginal_gated = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        short_funding_meaningful_threshold=0.0003,
    )
    assert marginal.short_score > marginal_gated.short_score
    assert any("positive" in reason for reason in marginal.reasons)
    assert not any("positive" in reason for reason in marginal_gated.reasons)
    assert any("acceptable range" in reason for reason in marginal_gated.reasons)


# ── 4) SHORT-only RSI-oversold exhaustion gate ────────────────────────────────

def test_short_rsi_oversold_gate_blocks_when_enabled():
    """
    RSI already oversold means the down move has likely already played out —
    exactly the setup that snaps back into a losing bounce. Disabled by
    default (0.0); blocks once short_rsi_oversold_max is set.
    """
    oversold_indicators = replace(_short_setup_indicators(), rsi=20.0)

    unaffected = score_signal(
        oversold_indicators,
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
    )
    assert unaffected.signal == "SHORT"

    blocked = score_signal(
        oversold_indicators,
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        short_rsi_oversold_max=25.0,
    )
    assert blocked.signal == "NO_TRADE"
    assert "oversold" in blocked.reasons[0]


# ── 5) Asymmetric entry-score threshold for SHORT ─────────────────────────────

def test_short_entry_score_threshold_override_raises_the_bar():
    """
    A SHORT-only threshold override can require a higher score than LONG's
    entry_score_threshold, without changing that shared threshold at all.
    """
    baseline = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
    )
    assert baseline.signal == "SHORT"

    raised_threshold = baseline.short_score + 1
    raised = score_signal(
        _short_setup_indicators(),
        trend_state=TrendState.CONFIRMED_DOWNTREND,
        open_interest_change_percent=1.2,
        funding_rate=0.0002,
        top_ratio_direction=-0.04,
        short_entry_score_threshold=raised_threshold,
    )
    assert raised.signal == "NO_TRADE"
    assert f"below the {raised_threshold} entry threshold" in raised.reasons[0]

