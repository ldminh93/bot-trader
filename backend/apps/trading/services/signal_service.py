from dataclasses import dataclass

from .indicator_service import IndicatorResult
from .trend_service import (
    TrendState,
    calculate_slope,
    is_cvd_falling,
    is_cvd_rising,
    is_delta_negative,
    is_delta_positive,
    risk_multiplier_for_state,
)

MAX_ENTRY_DISTANCE_ATR = 1.0
DEFAULT_ENTRY_SCORE_THRESHOLD = 85


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


def score_signal(
    signal_data: IndicatorResult,
    trend_state: TrendState | str,
    open_interest_change_percent: float,
    funding_rate: float,
    top_ratio_direction: float,
    enable_long: bool = True,
    enable_short: bool = True,
    entry_score_threshold: int = DEFAULT_ENTRY_SCORE_THRESHOLD,
) -> SignalResult:
    state = TrendState(trend_state)
    long_score = 0
    short_score = 0
    long_reasons: list[str] = []
    short_reasons: list[str] = []
    candles = signal_data.candles
    deltas = [float(row["delta"]) for row in candles]
    cvds = [float(row["cvd"]) for row in candles]
    ma7_slope = calculate_slope(
        [row["ma7"] for row in candles if row.get("ma7") is not None]
    )
    ma25_slope = calculate_slope(
        [row["ma25"] for row in candles if row.get("ma25") is not None]
    )
    oi_increasing = open_interest_change_percent > 0

    if state == TrendState.CONFIRMED_UPTREND:
        long_score += 30
        long_reasons.append("confirmed uptrend")
    elif state == TrendState.EARLY_UPTREND:
        long_score += 22
        long_reasons.append("early uptrend")
    if state == TrendState.CONFIRMED_DOWNTREND:
        short_score += 30
        short_reasons.append("confirmed downtrend")
    elif state == TrendState.EARLY_DOWNTREND:
        short_score += 22
        short_reasons.append("early downtrend")

    if signal_data.ma7 > signal_data.ma25:
        long_score += 15
        long_reasons.append("MA7 is above MA25")
    if signal_data.ma7 < signal_data.ma25:
        short_score += 15
        short_reasons.append("MA7 is below MA25")
    if ma7_slope > 0:
        long_score += 8
        long_reasons.append("MA7 slope is positive")
    if ma7_slope < 0:
        short_score += 8
        short_reasons.append("MA7 slope is negative")
    if ma25_slope > 0:
        long_score += 8
        long_reasons.append("MA25 slope is positive")
    if ma25_slope < 0:
        short_score += 8
        short_reasons.append("MA25 slope is negative")
    if signal_data.price > signal_data.ma25:
        long_score += 10
        long_reasons.append("price is above MA25")
    if signal_data.price < signal_data.ma25:
        short_score += 10
        short_reasons.append("price is below MA25")
    if signal_data.price > signal_data.ma99:
        long_score += 5
        long_reasons.append("price is above MA99")
    if signal_data.price < signal_data.ma99:
        short_score += 5
        short_reasons.append("price is below MA99")
    if is_delta_positive(deltas):
        long_score += 15
        long_reasons.append("last 3 deltas are positive")
    if is_delta_negative(deltas):
        short_score += 15
        short_reasons.append("last 3 deltas are negative")
    if is_cvd_rising(cvds):
        long_score += 10
        long_reasons.append("CVD is rising")
    if is_cvd_falling(cvds):
        short_score += 10
        short_reasons.append("CVD is falling")
    if oi_increasing:
        long_score += 15
        short_score += 15
        long_reasons.append("open interest is increasing")
        short_reasons.append("open interest is increasing")
    if -0.0003 <= funding_rate <= 0.0005:
        long_score += 8
        long_reasons.append("funding is acceptable")
    if -0.0005 <= funding_rate <= 0.0003:
        short_score += 8
        short_reasons.append("funding is acceptable")
    if top_ratio_direction > 0:
        long_score += 5
        long_reasons.append("top trader position ratio is rising")
    if top_ratio_direction < 0:
        short_score += 5
        short_reasons.append("top trader position ratio is falling")
    if signal_data.volume > signal_data.volume_ma20:
        long_score += 8
        short_score += 8
        long_reasons.append("volume is above volume MA20")
        short_reasons.append("volume is above volume MA20")

    multiplier = risk_multiplier_for_state(state)
    if state == TrendState.SIDEWAY:
        return SignalResult(
            "NO_TRADE",
            long_score,
            short_score,
            ["trend state is SIDEWAY"],
            state.value,
            0.0,
        )
    if state == TrendState.WEAK_DOWNTREND:
        return SignalResult(
            "NO_TRADE",
            long_score,
            short_score,
            ["weak downtrend blocks new SHORT entries"],
            state.value,
            0.0,
        )
    if (
        enable_long
        and state in {TrendState.EARLY_UPTREND, TrendState.CONFIRMED_UPTREND}
        and long_score >= entry_score_threshold
    ):
        location_reason = entry_location_block_reason(
            "LONG",
            signal_data.price,
            signal_data.ma7,
            signal_data.ma25,
            signal_data.atr,
        )
        if location_reason:
            return SignalResult(
                "NO_TRADE",
                long_score,
                short_score,
                [location_reason],
                state.value,
                multiplier,
            )
        return SignalResult(
            "LONG",
            long_score,
            short_score,
            long_reasons,
            state.value,
            multiplier,
        )
    if (
        enable_short
        and state in {TrendState.EARLY_DOWNTREND, TrendState.CONFIRMED_DOWNTREND}
        and short_score >= entry_score_threshold
    ):
        location_reason = entry_location_block_reason(
            "SHORT",
            signal_data.price,
            signal_data.ma7,
            signal_data.ma25,
            signal_data.atr,
        )
        if location_reason:
            return SignalResult(
                "NO_TRADE",
                long_score,
                short_score,
                [location_reason],
                state.value,
                multiplier,
            )
        return SignalResult(
            "SHORT",
            long_score,
            short_score,
            short_reasons,
            state.value,
            multiplier,
        )

    preferred_score = long_score if "UPTREND" in state.value else short_score
    direction = "LONG" if "UPTREND" in state.value else "SHORT"
    return SignalResult(
        "NO_TRADE",
        long_score,
        short_score,
        [f"{direction} score {preferred_score} is below the {entry_score_threshold} entry threshold"],
        state.value,
        multiplier,
    )
