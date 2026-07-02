from enum import Enum
from typing import Sequence

from .indicator_service import IndicatorResult


class TrendState(str, Enum):
    SIDEWAY = "SIDEWAY"
    EARLY_UPTREND = "EARLY_UPTREND"
    CONFIRMED_UPTREND = "CONFIRMED_UPTREND"
    WEAK_UPTREND = "WEAK_UPTREND"
    EARLY_DOWNTREND = "EARLY_DOWNTREND"
    CONFIRMED_DOWNTREND = "CONFIRMED_DOWNTREND"
    WEAK_DOWNTREND = "WEAK_DOWNTREND"


def calculate_slope(series: Sequence[float], lookback: int = 5) -> float:
    values = [float(value) for value in series if value is not None]
    if len(values) < 2:
        return 0.0
    window = values[-lookback:]
    return (window[-1] - window[0]) / max(len(window) - 1, 1)


def is_oi_increasing(oi_series: Sequence[float], lookback: int = 3) -> bool:
    values = [float(value) for value in oi_series if value is not None][-lookback:]
    return len(values) >= 2 and values[-1] > values[0]


def is_oi_flat(
    oi_series: Sequence[float],
    lookback: int = 5,
    threshold_percent: float = 0.2,
) -> bool:
    values = [float(value) for value in oi_series if value is not None][-lookback:]
    if len(values) < 2 or values[0] == 0:
        return False
    change_percent = abs((values[-1] - values[0]) / values[0] * 100)
    return change_percent < threshold_percent


def is_delta_positive(delta_series: Sequence[float], lookback: int = 3) -> bool:
    values = [float(value) for value in delta_series][-lookback:]
    return len(values) == lookback and all(value > 0 for value in values)


def is_delta_negative(delta_series: Sequence[float], lookback: int = 3) -> bool:
    values = [float(value) for value in delta_series][-lookback:]
    return len(values) == lookback and all(value < 0 for value in values)


def is_cvd_rising(cvd_series: Sequence[float], lookback: int = 3) -> bool:
    values = [float(value) for value in cvd_series][-lookback:]
    return len(values) >= 2 and values[-1] > values[0]


def is_cvd_falling(cvd_series: Sequence[float], lookback: int = 3) -> bool:
    values = [float(value) for value in cvd_series][-lookback:]
    return len(values) >= 2 and values[-1] < values[0]


def is_bullish_reversal_pattern(
    candles: Sequence[dict],
    red_count: int = 3,
    green_count: int = 2,
) -> bool:
    needed = red_count + green_count
    if len(candles) < needed:
        return False
    window = candles[-needed:]
    reds, greens = window[:red_count], window[red_count:]
    return all(float(c["close"]) < float(c["open"]) for c in reds) and all(
        float(c["close"]) > float(c["open"]) for c in greens
    )


def are_mas_compressed(
    ma7: float,
    ma25: float,
    ma99: float,
    atr: float,
    threshold: float = 0.3,
) -> bool:
    if atr <= 0:
        return True
    spread = max(ma7, ma25, ma99) - min(ma7, ma25, ma99)
    return spread < atr * threshold


def delta_changes_direction_frequently(
    delta_series: Sequence[float],
    lookback: int = 5,
) -> bool:
    values = [float(value) for value in delta_series][-lookback:]
    if len(values) < 3:
        return False
    signs = [1 if value > 0 else -1 if value < 0 else 0 for value in values]
    changes = sum(
        1
        for previous, current in zip(signs, signs[1:])
        if previous and current and previous != current
    )
    return changes >= 2


def detect_trend_state(
    result: IndicatorResult,
    adx_min: float,
    oi_series: Sequence[float],
) -> TrendState:
    candles = result.candles
    ma7_series = [row["ma7"] for row in candles if row.get("ma7") is not None]
    ma25_series = [row["ma25"] for row in candles if row.get("ma25") is not None]
    ma99_series = [row["ma99"] for row in candles if row.get("ma99") is not None]
    delta_series = [float(row["delta"]) for row in candles]
    cvd_series = [float(row["cvd"]) for row in candles]

    ma7_slope = calculate_slope(ma7_series)
    ma25_slope = calculate_slope(ma25_series)
    ma99_slope = calculate_slope(ma99_series)
    oi_increasing = is_oi_increasing(oi_series)
    oi_decreasing = len(oi_series) >= 2 and float(oi_series[-1]) < float(oi_series[0])
    oi_flat = is_oi_flat(oi_series)
    delta_positive = is_delta_positive(delta_series)
    delta_negative = is_delta_negative(delta_series)
    cvd_rising = is_cvd_rising(cvd_series)
    cvd_falling = is_cvd_falling(cvd_series)

    if (
        result.adx < adx_min
        or (result.atr_ma20 > 0 and result.atr < result.atr_ma20 * 0.8)
        or are_mas_compressed(result.ma7, result.ma25, result.ma99, result.atr)
        or (oi_flat and delta_changes_direction_frequently(delta_series))
    ):
        return TrendState.SIDEWAY

    if (
        result.ma7 > result.ma25
        and (
            delta_series[-1] < 0
            or cvd_falling
            or oi_decreasing
            or result.price < result.ma25
        )
    ):
        return TrendState.WEAK_UPTREND

    if (
        result.ma7 < result.ma25
        and (
            delta_series[-1] > 0
            or cvd_rising
            or oi_decreasing
            or result.price > result.ma25
        )
    ):
        return TrendState.WEAK_DOWNTREND

    if (
        result.ma7 > result.ma25 > result.ma99
        and ma25_slope > 0
        and ma99_slope >= 0
        and result.price > result.ma25
        and oi_increasing
    ):
        return TrendState.CONFIRMED_UPTREND

    if (
        result.ma7 < result.ma25 < result.ma99
        and ma25_slope < 0
        and ma99_slope <= 0
        and result.price < result.ma25
        and oi_increasing
    ):
        return TrendState.CONFIRMED_DOWNTREND

    if (
        result.ma7 > result.ma25
        and ma7_slope > 0
        and ma25_slope > 0
        and result.price > result.ma25
        and delta_positive
        and oi_increasing
    ):
        return TrendState.EARLY_UPTREND

    if (
        result.ma7 < result.ma25
        and ma7_slope < 0
        and ma25_slope < 0
        and result.price < result.ma25
        and delta_negative
        and oi_increasing
    ):
        return TrendState.EARLY_DOWNTREND

    return TrendState.SIDEWAY


def format_compact(value: float) -> str:
    number = float(value)
    sign = "-" if number < 0 else ""
    magnitude = abs(number)
    for suffix, threshold in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if magnitude >= threshold:
            return f"{sign}{magnitude / threshold:.2f}{suffix}"
    if magnitude >= 1:
        return f"{sign}{magnitude:.2f}"
    return f"{sign}{magnitude:.4f}"


def explain_trend_state(
    result: IndicatorResult,
    adx_min: float,
    oi_series: Sequence[float],
    trend_state: TrendState,
) -> list[str]:
    candles = result.candles
    delta_series = [float(row["delta"]) for row in candles]
    cvd_series = [float(row["cvd"]) for row in candles]
    reasons: list[str] = []

    if trend_state == TrendState.SIDEWAY:
        if result.adx < adx_min:
            reasons.append(f"ADX {result.adx:.1f} is below {adx_min:.1f}")
        if result.atr_ma20 > 0 and result.atr < result.atr_ma20 * 0.8:
            reasons.append(
                f"ATR ({format_compact(result.atr)}) is below 80% of ATR MA20 "
                f"({format_compact(result.atr_ma20)})"
            )
        if are_mas_compressed(result.ma7, result.ma25, result.ma99, result.atr):
            spread = max(result.ma7, result.ma25, result.ma99) - min(result.ma7, result.ma25, result.ma99)
            reasons.append(
                f"MA7, MA25, and MA99 are compressed (spread {format_compact(spread)})"
            )
        if is_oi_flat(oi_series) and delta_changes_direction_frequently(delta_series):
            reasons.append(
                f"open interest is flat ({format_compact(oi_series[-1])}) "
                f"while delta changes direction frequently"
            )
        if not reasons:
            reasons.append("trend conditions are not aligned")
    elif trend_state == TrendState.WEAK_UPTREND:
        if delta_series[-1] < 0:
            reasons.append(f"delta turned negative ({format_compact(delta_series[-1])})")
        if is_cvd_falling(cvd_series):
            reasons.append(f"CVD is falling ({format_compact(cvd_series[-1])})")
        if len(oi_series) >= 2 and float(oi_series[-1]) < float(oi_series[0]):
            reasons.append(
                f"open interest is decreasing ({format_compact(oi_series[0])} → "
                f"{format_compact(oi_series[-1])})"
            )
        if result.price < result.ma25:
            reasons.append(
                f"price ({format_compact(result.price)}) closed below MA25 "
                f"({format_compact(result.ma25)})"
            )
    elif trend_state == TrendState.WEAK_DOWNTREND:
        if delta_series[-1] > 0:
            reasons.append(f"delta turned positive ({format_compact(delta_series[-1])})")
        if is_cvd_rising(cvd_series):
            reasons.append(f"CVD is rising ({format_compact(cvd_series[-1])})")
        if len(oi_series) >= 2 and float(oi_series[-1]) < float(oi_series[0]):
            reasons.append(
                f"open interest is decreasing ({format_compact(oi_series[0])} → "
                f"{format_compact(oi_series[-1])})"
            )
        if result.price > result.ma25:
            reasons.append(
                f"price ({format_compact(result.price)}) closed above MA25 "
                f"({format_compact(result.ma25)})"
            )
    elif trend_state in {TrendState.EARLY_UPTREND, TrendState.EARLY_DOWNTREND}:
        reasons.append("early trend conditions are aligned")
    else:
        reasons.append("confirmed trend conditions are aligned")
    return reasons


def risk_multiplier_for_state(trend_state: TrendState | str) -> float:
    if trend_state in {
        TrendState.EARLY_UPTREND,
        TrendState.EARLY_DOWNTREND,
        TrendState.WEAK_UPTREND,
    }:
        return 0.5
    if trend_state in {
        TrendState.CONFIRMED_UPTREND,
        TrendState.CONFIRMED_DOWNTREND,
    }:
        return 1.0
    return 0.0
