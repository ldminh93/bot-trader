from dataclasses import dataclass

from .indicator_service import (
    EntryQualityResult,
    IndicatorResult,
    calculate_oi_acceleration,
    detect_long_entry_quality,
    detect_short_entry_quality,
)
from .trend_service import (
    TrendState,
    calculate_cvd_slope,
    calculate_slope,
    is_bullish_reversal_pattern,
    is_cvd_falling,
    is_cvd_rising,
    is_delta_negative,
    is_delta_positive,
    risk_multiplier_for_state,
)

SIDEWAY_REVERSAL_RISK_MULTIPLIER = 0.5

# ── Entry-distance gate ────────────────────────────────────────────────────────
# Maximum distance from the nearest MA expressed in ATR units.
# Prevents chasing price after it has already moved far from the MA zone.
MAX_ENTRY_DISTANCE_ATR = 1.0

# ── Score thresholds ───────────────────────────────────────────────────────────
# Raised from 85 → 70 because the new scoring is tighter (redundant conditions
# removed, only high-information signals retained).  A clean pullback+rejection
# setup with CVD and delta confirmation easily reaches 70; a raw breakout
# without a retrace cannot reach this level.
DEFAULT_ENTRY_SCORE_THRESHOLD = 70
EARLY_ENTRY_SCORE_THRESHOLD = DEFAULT_ENTRY_SCORE_THRESHOLD
CONFIRMED_ENTRY_SCORE_THRESHOLD = DEFAULT_ENTRY_SCORE_THRESHOLD

# ── ATR regime gates ───────────────────────────────────────────────────────────
# Require ATR to be between 70 % and 250 % of its 20-period MA.
# Below 0.7 → volatility is contracting / market is asleep; risk of whipsaw.
# Above 2.5 → blow-off / news spike; spread costs and slippage are extreme.
ATR_REGIME_MIN_RATIO = 0.7
ATR_REGIME_MAX_RATIO = 2.5

# ── Minimum ADX gate ───────────────────────────────────────────────────────────
# Only enter when the market is genuinely trending.  ADX < MIN_ADX means the
# market is ranging and the trend-following logic has no edge.
MIN_ADX_FOR_ENTRY = 20.0

# ── Funding-rate gate ──────────────────────────────────────────────────────────
# For SHORT: positive funding means longs are paying shorts → crowded long,
# favours shorting.  For LONG: negative funding means shorts are paying longs.
# Acceptable ranges kept for the non-directional path (sideway reversals).
LONG_FUNDING_ACCEPTABLE_RANGE = (-0.0003, 0.0005)
SHORT_FUNDING_ACCEPTABLE_RANGE = (-0.0005, 0.0003)


@dataclass(frozen=True)
class SignalResult:
    signal: str
    long_score: int
    short_score: int
    reasons: list[str]
    trend_state: str
    risk_multiplier: float


def entry_location_block_reason(
    side: str,
    price: float,
    ma7: float,
    ma25: float,
    atr: float,
    max_distance_atr: float = MAX_ENTRY_DISTANCE_ATR,
) -> str | None:
    if atr <= 0:
        return "ATR is unavailable for the entry-location check"
    moving_averages = [("MA7", ma7), ("MA25", ma25)]
    if side == "LONG":
        supports = [(name, value) for name, value in moving_averages if value < price]
        if not supports:
            return "LONG entry has no MA7/MA25 support below price"
        name, nearest_support = max(supports, key=lambda item: item[1])
        distance_atr = (price - nearest_support) / atr
        if distance_atr > max_distance_atr:
            return (
                f"LONG entry is overextended: price is {distance_atr:.2f} ATR "
                f"above {name} (maximum {max_distance_atr:.2f} ATR)"
            )
        return None
    if side == "SHORT":
        resistances = [(name, value) for name, value in moving_averages if value > price]
        if not resistances:
            return "SHORT entry has no MA7/MA25 resistance above price"
        name, nearest_resistance = min(resistances, key=lambda item: item[1])
        distance_atr = (nearest_resistance - price) / atr
        if distance_atr > max_distance_atr:
            return (
                f"SHORT entry is overextended: price is {distance_atr:.2f} ATR "
                f"below {name} (maximum {max_distance_atr:.2f} ATR)"
            )
        return None
    return f"Unsupported entry side: {side}"


def entry_score_threshold_for_state(state: TrendState) -> int:
    return DEFAULT_ENTRY_SCORE_THRESHOLD


# ─────────────────────────────────────────────────────────────────────────────
# score_signal — redesigned entry logic
# ─────────────────────────────────────────────────────────────────────────────
#
# ARCHITECTURE: Two-layer filter
# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Hard gates (mandatory; any failure → NO_TRADE immediately)
#   These are structural requirements that define *whether* an entry is valid.
#   They do not score — they either pass or fail.
#
#   [G1] Trend state — must be downtrend/uptrend (not sideway / weak)
#   [G2] MA alignment — MA7 < MA25 for SHORT; MA7 > MA25 for LONG
#   [G3] Price < MA99 for SHORT; price > MA99 for LONG (macro direction)
#   [G4] ADX regime — ADX must exceed MIN_ADX_FOR_ENTRY to confirm a trend
#        is actually present (prevents ranging-market entries)
#   [G5] ATR regime — ATR must be between ATR_REGIME_MIN_RATIO and
#        ATR_REGIME_MAX_RATIO × ATR_MA20.  Too low = dead market; too high =
#        blow-off spike where spread cost and slippage destroy edge.
#   [G6] Pullback detected — price must be within the MA25 zone
#        (enabled by pullback_entry_enabled).  This is the *single biggest
#        source of improvement*: stops the bot from entering mid-impulse
#        after the move has already occurred.
#   [G7] Rejection candle — current candle must show directional wick
#        rejection at the MA zone.  Confirms that counter-trend participants
#        are being absorbed.
#
# Layer 2 — Quality score (scored; must reach entry_score_threshold)
#   These measure the *quality* of the setup's flow confirmation.
#   They are only evaluated after all hard gates have passed.
#
#   Conditions REMOVED from the original scoring and why:
#   ┌─────────────────────────────────────────────────────────────────────────┐
#   │  REMOVED          │ REASON                                              │
#   ├─────────────────────────────────────────────────────────────────────────┤
#   │  MA7 slope        │ Redundant: trend state detection already uses MA    │
#   │  MA25 slope       │ slopes as input.  Double-counting inflates score of │
#   │                   │ setups that have strong trend but weak entry.        │
#   ├─────────────────────────────────────────────────────────────────────────┤
#   │  Price < MA25     │ Redundant: MA7 < MA25 (G2) and confirmed downtrend  │
#   │  Price > MA25     │ already encodes this relationship.                  │
#   ├─────────────────────────────────────────────────────────────────────────┤
#   │  Raw OI increase  │ Direction-neutral (scored +15 to BOTH LONG and      │
#   │                   │ SHORT).  Replaced by OI acceleration, which measures│
#   │                   │ whether new positions are *actively entering* rather │
#   │                   │ than stale positions holding.                        │
#   ├─────────────────────────────────────────────────────────────────────────┤
#   │  Volume > MA20    │ Conflates impulse breakout volume (bad for pullback  │
#   │                   │ entries) with rejection volume (good).  Replaced by  │
#   │                   │ directional volume pattern: low on pullback + high  │
#   │                   │ on rejection = textbook absorption signal.           │
#   └─────────────────────────────────────────────────────────────────────────┘
#
#   Score weights (SHORT mirror is identical with reversed polarity):
#
#   Rank │ Condition                    │ Pts │ Why
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     1  │ CVD slope falling (5-bar)    │  20 │ Sustained distribution across
#        │                              │     │ multiple candles is far more
#        │                              │     │ signal than a 3-candle check.
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     2  │ Delta negative 3+ candles    │  15 │ Immediate selling pressure on
#        │ (12 pts for 2 consecutive)   │     │ the rejection candle(s).
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     3  │ Rejection volume > 1.2×      │  10 │ Sellers showing up with size
#        │ vol_ma20                     │     │ confirms conviction, not noise.
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     4  │ Pullback volume < 0.85×      │  10 │ Low-volume retrace = no genuine
#        │ vol_ma20                     │     │ buying conviction; smart money
#        │                              │     │ is not accumulating into bounce.
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     5  │ OI acceleration > 0          │  12 │ New shorts (not old longs
#        │                              │     │ holding) are the fuel for the
#        │                              │     │ next leg down.
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     6  │ Funding rate > 0 for SHORT   │   8 │ Positive funding = crowded long;
#        │ (< 0 for LONG)               │     │ structurally favours the short.
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     7  │ Top trader ratio falling     │   7 │ Large traders net short = smart
#        │                              │     │ money alignment.
#   ─────┼──────────────────────────────┼─────┼────────────────────────────────
#     8  │ Confirmed (vs Early) trend   │   8 │ Small bonus for higher-quality
#        │                              │     │ trend context.
#   ─────┴──────────────────────────────┴─────┴────────────────────────────────
#   Maximum possible score: 90   Default threshold: 55
#   Minimum viable setup: CVD(20) + delta(15) + vol_pullback(10) = 45 → must
#   add at least OI acceleration or rejection volume to clear 55.
# ─────────────────────────────────────────────────────────────────────────────
def score_signal(
    signal_data: IndicatorResult,
    trend_state: TrendState | str,
    open_interest_change_percent: float,
    funding_rate: float,
    top_ratio_direction: float,
    enable_long: bool = True,
    enable_short: bool = True,
    entry_score_threshold: int = DEFAULT_ENTRY_SCORE_THRESHOLD,
    pullback_entry_enabled: bool = True,
    max_entry_distance_atr: float = MAX_ENTRY_DISTANCE_ATR,
    oi_history: list[float] | None = None,
) -> SignalResult:
    state = TrendState(trend_state)
    candles = signal_data.candles
    deltas = [float(row["delta"]) for row in candles]
    cvds = [float(row["cvd"]) for row in candles]
    multiplier = risk_multiplier_for_state(state)

    # ── Sideway: special reversal pattern (unchanged logic) ──────────────────
    if state == TrendState.SIDEWAY:
        if (
            enable_long
            and is_bullish_reversal_pattern(candles)
            and signal_data.volume > signal_data.volume_ma20
            and deltas[-1] > 0
        ):
            location_reason = (
                entry_location_block_reason(
                    "LONG",
                    signal_data.price,
                    signal_data.ma7,
                    signal_data.ma25,
                    signal_data.atr,
                    max_entry_distance_atr,
                )
                if pullback_entry_enabled
                else None
            )
            if location_reason:
                return SignalResult("NO_TRADE", 0, 0, [location_reason], state.value, 0.0)
            return SignalResult(
                "LONG", 0, 0,
                ["bullish reversal: 3 red candles then 2 green candles "
                 "with rising volume and positive delta"],
                state.value,
                SIDEWAY_REVERSAL_RISK_MULTIPLIER,
            )
        return SignalResult("NO_TRADE", 0, 0, ["trend state is SIDEWAY"], state.value, 0.0)

    if state == TrendState.WEAK_DOWNTREND:
        return SignalResult(
            "NO_TRADE", 0, 0, ["weak downtrend blocks new SHORT entries"], state.value, 0.0
        )

    # ── Shared pre-computation ────────────────────────────────────────────────
    atr = signal_data.atr
    atr_ma20 = signal_data.atr_ma20

    # ── Hard Gate G4: ADX regime ──────────────────────────────────────────────
    if signal_data.adx < MIN_ADX_FOR_ENTRY:
        reason = (
            f"ADX {signal_data.adx:.1f} is below the minimum {MIN_ADX_FOR_ENTRY:.0f} "
            f"required for trend entries"
        )
        return SignalResult("NO_TRADE", 0, 0, [reason], state.value, multiplier)

    # ── Hard Gate G5: ATR volatility regime ───────────────────────────────────
    if atr_ma20 > 0:
        atr_ratio = atr / atr_ma20
        if atr_ratio < ATR_REGIME_MIN_RATIO:
            return SignalResult(
                "NO_TRADE", 0, 0,
                [f"ATR is contracting ({atr_ratio:.2f}× ATR_MA20); market lacks momentum"],
                state.value, multiplier,
            )
        if atr_ratio > ATR_REGIME_MAX_RATIO:
            return SignalResult(
                "NO_TRADE", 0, 0,
                [f"ATR is excessive ({atr_ratio:.2f}× ATR_MA20); avoid blow-off entry"],
                state.value, multiplier,
            )

    # ── OI acceleration (shared) ──────────────────────────────────────────────
    oi_accel = calculate_oi_acceleration(oi_history) if oi_history else 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # SHORT path
    # ─────────────────────────────────────────────────────────────────────────
    if enable_short and state in {TrendState.EARLY_DOWNTREND, TrendState.CONFIRMED_DOWNTREND}:

        # ── Compute base quality score FIRST (pre-gate) ──────────────────────
        # These conditions can be evaluated regardless of whether the pullback
        # gate passes.  Carrying this score through NO_TRADE returns ensures the
        # scoreboard always shows a meaningful relative ranking — "how close is
        # this symbol to a qualifying SHORT?" — rather than a flat zero.
        short_score = 0
        short_reasons: list[str] = []

        cvd_slope = calculate_cvd_slope(cvds, lookback=5)
        if cvd_slope < 0:
            short_score += 20
            short_reasons.append("CVD slope is falling (sustained selling flow)")

        if is_delta_negative(deltas, lookback=3):
            short_score += 15
            short_reasons.append("last 3 deltas are negative")
        elif is_delta_negative(deltas, lookback=2):
            short_score += 12
            short_reasons.append("last 2 deltas are negative")

        if oi_accel > 0:
            short_score += 12
            short_reasons.append(f"open interest is accelerating (+{oi_accel:.6f})")

        if funding_rate > 0:
            short_score += 8
            short_reasons.append(f"funding rate is positive ({funding_rate:.4%}); longs paying")
        elif SHORT_FUNDING_ACCEPTABLE_RANGE[0] <= funding_rate <= SHORT_FUNDING_ACCEPTABLE_RANGE[1]:
            short_score += 4
            short_reasons.append("funding rate is in acceptable range")

        if top_ratio_direction < 0:
            short_score += 7
            short_reasons.append("top trader position ratio is falling")

        if state == TrendState.CONFIRMED_DOWNTREND:
            short_score += 8
            short_reasons.append("confirmed downtrend")

        # ── Hard Gate G2: MA alignment ────────────────────────────────────────
        if signal_data.ma7 >= signal_data.ma25:
            return SignalResult(
                "NO_TRADE", 0, short_score,
                ["SHORT requires MA7 < MA25"],
                state.value, multiplier,
            )

        # ── Hard Gate G3: macro direction ─────────────────────────────────────
        if signal_data.price >= signal_data.ma99:
            return SignalResult(
                "NO_TRADE", 0, short_score,
                ["SHORT requires price below MA99"],
                state.value, multiplier,
            )

        if pullback_entry_enabled:
            eq = detect_short_entry_quality(
                candles,
                atr,
                signal_data.ma25,
                signal_data.volume_ma20,
            )

            # Hard Gate G6: pullback zone
            if not eq.has_pullback:
                return SignalResult(
                    "NO_TRADE", 0, short_score,
                    [
                        f"SHORT entry blocked: price is not in the MA25 pullback zone "
                        f"(price {signal_data.price:.4f}, MA25 {signal_data.ma25:.4f})"
                    ],
                    state.value, multiplier,
                )

            # Hard Gate G7: rejection candle
            if not eq.has_rejection_candle:
                return SignalResult(
                    "NO_TRADE", 0, short_score,
                    [
                        f"SHORT entry blocked: no bearish rejection candle at MA25 "
                        f"(upper wick ratio {eq.rejection_wick_ratio:.2f})"
                    ],
                    state.value, multiplier,
                )

            # Score: volume pattern (only meaningful after pullback confirmed)
            if eq.vol_pullback_ratio < 0.85:
                short_score += 10
                short_reasons.append(
                    f"low pullback volume ({eq.vol_pullback_ratio:.2f}× vol_ma20)"
                )
            if eq.vol_rejection_ratio > 1.2:
                short_score += 10
                short_reasons.append(
                    f"high rejection volume ({eq.vol_rejection_ratio:.2f}× vol_ma20)"
                )
        else:
            # Legacy path: use distance-based location check only
            location_reason = entry_location_block_reason(
                "SHORT",
                signal_data.price,
                signal_data.ma7,
                signal_data.ma25,
                atr,
                max_entry_distance_atr,
            )
            if location_reason:
                return SignalResult("NO_TRADE", 0, short_score, [location_reason], state.value, multiplier)

        if short_score >= entry_score_threshold:
            return SignalResult(
                "SHORT", 0, short_score, short_reasons, state.value, multiplier
            )
        return SignalResult(
            "NO_TRADE", 0, short_score,
            [f"SHORT score {short_score} is below the {entry_score_threshold} entry threshold"],
            state.value, multiplier,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # LONG path
    # ─────────────────────────────────────────────────────────────────────────
    if enable_long and state in {TrendState.EARLY_UPTREND, TrendState.CONFIRMED_UPTREND}:

        # ── Compute base quality score FIRST (pre-gate) ──────────────────────
        long_score = 0
        long_reasons: list[str] = []

        cvd_slope = calculate_cvd_slope(cvds, lookback=5)
        if cvd_slope > 0:
            long_score += 20
            long_reasons.append("CVD slope is rising (sustained buying flow)")

        if is_delta_positive(deltas, lookback=3):
            long_score += 15
            long_reasons.append("last 3 deltas are positive")
        elif is_delta_positive(deltas, lookback=2):
            long_score += 12
            long_reasons.append("last 2 deltas are positive")

        if oi_accel > 0:
            long_score += 12
            long_reasons.append(f"open interest is accelerating (+{oi_accel:.6f})")

        if funding_rate < 0:
            long_score += 8
            long_reasons.append(f"funding rate is negative ({funding_rate:.4%}); shorts paying")
        elif LONG_FUNDING_ACCEPTABLE_RANGE[0] <= funding_rate <= LONG_FUNDING_ACCEPTABLE_RANGE[1]:
            long_score += 4
            long_reasons.append("funding rate is in acceptable range")

        if top_ratio_direction > 0:
            long_score += 7
            long_reasons.append("top trader position ratio is rising")

        if state == TrendState.CONFIRMED_UPTREND:
            long_score += 8
            long_reasons.append("confirmed uptrend")

        # ── Hard Gate G2: MA alignment ────────────────────────────────────────
        if signal_data.ma7 <= signal_data.ma25:
            return SignalResult(
                "NO_TRADE", long_score, 0,
                ["LONG requires MA7 > MA25"],
                state.value, multiplier,
            )

        # ── Hard Gate G3: macro direction ─────────────────────────────────────
        if signal_data.price <= signal_data.ma99:
            return SignalResult(
                "NO_TRADE", long_score, 0,
                ["LONG requires price above MA99"],
                state.value, multiplier,
            )

        if pullback_entry_enabled:
            eq = detect_long_entry_quality(
                candles,
                atr,
                signal_data.ma25,
                signal_data.volume_ma20,
            )

            if not eq.has_pullback:
                return SignalResult(
                    "NO_TRADE", long_score, 0,
                    [
                        f"LONG entry blocked: price is not in the MA25 pullback zone "
                        f"(price {signal_data.price:.4f}, MA25 {signal_data.ma25:.4f})"
                    ],
                    state.value, multiplier,
                )

            if not eq.has_rejection_candle:
                return SignalResult(
                    "NO_TRADE", long_score, 0,
                    [
                        f"LONG entry blocked: no bullish rejection candle at MA25 "
                        f"(lower wick ratio {eq.rejection_wick_ratio:.2f})"
                    ],
                    state.value, multiplier,
                )

            # Score: volume pattern (only meaningful after pullback confirmed)
            if eq.vol_pullback_ratio < 0.85:
                long_score += 10
                long_reasons.append(
                    f"low pullback volume ({eq.vol_pullback_ratio:.2f}× vol_ma20)"
                )
            if eq.vol_rejection_ratio > 1.2:
                long_score += 10
                long_reasons.append(
                    f"high rejection volume ({eq.vol_rejection_ratio:.2f}× vol_ma20)"
                )
        else:
            location_reason = entry_location_block_reason(
                "LONG",
                signal_data.price,
                signal_data.ma7,
                signal_data.ma25,
                atr,
                max_entry_distance_atr,
            )
            if location_reason:
                return SignalResult("NO_TRADE", long_score, 0, [location_reason], state.value, multiplier)

        if long_score >= entry_score_threshold:
            return SignalResult(
                "LONG", long_score, 0, long_reasons, state.value, multiplier
            )
        return SignalResult(
            "NO_TRADE", long_score, 0,
            [f"LONG score {long_score} is below the {entry_score_threshold} entry threshold"],
            state.value, multiplier,
        )

    return SignalResult(
        "NO_TRADE", 0, 0,
        [f"no enabled signal direction matches trend state {state.value}"],
        state.value, multiplier,
    )

