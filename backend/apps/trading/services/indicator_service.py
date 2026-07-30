from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class EntryQualityResult:
    """
    Captures structural entry quality for a potential trade.

    Fields
    ------
    has_pullback : bool
        Price is within ``pullback_zone_atr`` ATR of the resistance/support MA,
        indicating a counter-trend retrace rather than a mid-impulse chase.
    pullback_candles : int
        Number of consecutive rising (for SHORT) or falling (for LONG) candles
        detected before the current bar — higher = deeper, more mature retrace.
    has_rejection_candle : bool
        Current candle shows a high-conviction reversal wick against the trend
        direction (upper wick for SHORT, lower wick for LONG), confirming
        sellers / buyers are defending the zone.
    rejection_wick_ratio : float
        Dominant wick size as a fraction of total candle range [0..1].
        Higher = more decisive rejection.
    vol_pullback_ratio : float
        Average volume during pullback candles normalised by vol_ma20.
        Values below 1.0 indicate a low-conviction retrace (desirable for
        trend-following entries — smart money not participating in the bounce).
    vol_rejection_ratio : float
        Volume on the current (rejection) candle normalised by vol_ma20.
        Values above 1.0 indicate expanding participation at the turning point.
    """

    has_pullback: bool
    pullback_candles: int
    has_rejection_candle: bool
    rejection_wick_ratio: float
    vol_pullback_ratio: float
    vol_rejection_ratio: float


def _upper_wick_ratio(candle: dict) -> float:
    """Upper wick as a fraction of total candle range. Returns 0 when range is zero."""
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])
    open_ = float(candle["open"])
    total_range = high - low
    if total_range < 1e-10:
        return 0.0
    body_top = max(open_, close)
    return (high - body_top) / total_range


def _lower_wick_ratio(candle: dict) -> float:
    """Lower wick as a fraction of total candle range. Returns 0 when range is zero."""
    high = float(candle["high"])
    low = float(candle["low"])
    close = float(candle["close"])
    open_ = float(candle["open"])
    total_range = high - low
    if total_range < 1e-10:
        return 0.0
    body_bottom = min(open_, close)
    return (body_bottom - low) / total_range


MIN_MA_GAP_PCT = 0.03


def _ma7_cross_recovery(
    candles: list[dict],
    direction: str,
    ma25: float,
    min_gap_pct: float = MIN_MA_GAP_PCT,
) -> bool:
    """
    Detect a 2-candle pullback-and-reclaim of MA7 without ever reaching MA25.

    In a strong trend price often dips below (LONG) / pokes above (SHORT) MA7
    for only a candle or two before the trend resumes — it never retraces far
    enough to enter the MA25 zone.  Requiring the MA25 zone check in that case
    means the bot misses clean continuation entries.

    Pattern (LONG): the previous candle is bearish (red) and closed on/below
    MA7 — the "decrease" — and the current candle has closed back above MA7
    — the "increase that cuts MA7".  Mirror for SHORT with a green previous
    candle closing back below MA7.

    MA7/MA25 must also be separated by at least ``min_gap_pct`` (relative to
    MA25) — when they're bunched together the market is sideways/choppy and
    a bare MA7 cross is noise rather than a trend continuation signal.
    """
    if len(candles) < 2 or ma25 == 0:
        return False
    prev, last = candles[-2], candles[-1]
    if last.get("ma7") is None or prev.get("ma7") is None:
        return False
    last_ma7 = float(last["ma7"])
    if abs(last_ma7 - ma25) / abs(ma25) < min_gap_pct:
        return False
    last_close = float(last["close"])
    prev_ma7 = float(prev["ma7"])
    prev_close = float(prev["close"])
    prev_open = float(prev["open"])
    if direction == "LONG":
        prev_is_red = prev_close < prev_open
        crossed_up = prev_close <= prev_ma7 and last_close > last_ma7
        return prev_is_red and crossed_up
    if direction == "SHORT":
        prev_is_green = prev_close > prev_open
        crossed_down = prev_close >= prev_ma7 and last_close < last_ma7
        return prev_is_green and crossed_down
    return False


@dataclass(frozen=True)
class MAStackReversalResult:
    """
    detected : bool
        Whether the reversal pattern fired.
    bottom_ma, middle_ma, top_ma : float
        MA7/MA25/MA99 sorted ascending by value (not by period) — only
        meaningful when ``detected`` is True.
    """

    detected: bool
    bottom_ma: float
    middle_ma: float
    top_ma: float


_EMPTY_MA_STACK_REVERSAL = MAStackReversalResult(False, 0.0, 0.0, 0.0)


def detect_ma_stack_reversal(
    candles: list[dict],
    ma7: float,
    ma25: float,
    ma99: float,
    direction: str,
    min_gap_pct: float = MIN_MA_GAP_PCT,
) -> MAStackReversalResult:
    """
    Detect an early trend-reversal entry: price crosses back through
    whichever of MA7/MA25/MA99 currently has the lowest (LONG) / highest
    (SHORT) value, while still sitting between it and the next MA in line.

    This is deliberately independent of the MA7>MA25 / price>MA99
    trend-confirmation gates used elsewhere (see score_signal G2/G3) — it's
    meant to catch a reversal *before* those gates would confirm a new
    trend, so it doesn't require them.

    LONG: sort the three MAs ascending (bottom < middle < top). Price must
    sit strictly between bottom and middle — it has just cleared bottom but
    hasn't reached middle yet.  The previous candle must be bearish and
    closed on/below bottom (the "decrease"); the current candle must have
    closed back above bottom (the "increase that cuts" it).  bottom/middle
    must be separated by at least ``min_gap_pct`` (relative to bottom) or
    the MA stack is too bunched together (sideways/choppy) for the cross to
    mean anything.

    SHORT mirrors this: price sits between middle and top, the previous
    candle is bullish and closed on/above top, and the current candle
    closed back below top.
    """
    if len(candles) < 2:
        return _EMPTY_MA_STACK_REVERSAL
    bottom, middle, top = sorted([float(ma7), float(ma25), float(ma99)])
    prev, last = candles[-2], candles[-1]
    last_close = float(last["close"])
    prev_close = float(prev["close"])
    prev_open = float(prev["open"])
    if direction == "LONG":
        if bottom == 0 or not (bottom < last_close < middle):
            return _EMPTY_MA_STACK_REVERSAL
        if (middle - bottom) / abs(bottom) < min_gap_pct:
            return _EMPTY_MA_STACK_REVERSAL
        prev_is_red = prev_close < prev_open
        crossed_up = prev_close <= bottom < last_close
        return MAStackReversalResult(prev_is_red and crossed_up, bottom, middle, top)
    if direction == "SHORT":
        if top == 0 or not (middle < last_close < top):
            return _EMPTY_MA_STACK_REVERSAL
        if (top - middle) / abs(top) < min_gap_pct:
            return _EMPTY_MA_STACK_REVERSAL
        prev_is_green = prev_close > prev_open
        crossed_down = prev_close >= top > last_close
        return MAStackReversalResult(prev_is_green and crossed_down, bottom, middle, top)
    return _EMPTY_MA_STACK_REVERSAL


def detect_short_entry_quality(
    candles: list[dict],
    atr: float,
    ma25: float,
    vol_ma20: float,
    pullback_zone_atr: float = 0.8,
    min_rejection_wick: float = 0.35,
) -> EntryQualityResult:
    """
    Assess whether conditions favour a high-quality SHORT entry.

    Pullback (hard-gate precondition)
    ----------------------------------
    Price must be sitting within ``pullback_zone_atr`` ATR below MA25, OR
    satisfy the MA7 cross-recovery: previous candle green and closed on/above
    MA7 (the bounce), current candle closed back below MA7 (the rejection),
    with MA7 and MA25 separated by at least ``MIN_MA_GAP_PCT`` to rule
    out a sideways/choppy market (see ``_ma7_cross_recovery``) — a shallower
    retrace that never reaches MA25 in a strong trend.  This prevents chasing
    price after it has already fallen far from resistance while still
    allowing fast continuation entries.

    Rejection candle (primary entry trigger)
    ----------------------------------------
    The current candle must show a bearish upper-wick rejection (upper wick
    ≥ ``min_rejection_wick`` of the total range) *and* a bearish close
    (close < open), OR satisfy the MA7 cross-recovery above (the reclaim
    itself stands in as the rejection signal). This confirms that sellers
    are defending the zone.

    Volume profile (quality filter)
    --------------------------------
    Healthy pullbacks have low volume (lack of genuine buying conviction).
    The rejection candle should have above-average volume, confirming
    aggressive selling into the bounce.

    Parameters
    ----------
    pullback_zone_atr : float
        Maximum distance below MA25 (in ATR units) that still counts as
        being "in the pullback zone" near resistance.
    min_rejection_wick : float
        Minimum upper-wick-to-range ratio required for a rejection candle.
    """
    _empty = EntryQualityResult(
        has_pullback=False,
        pullback_candles=0,
        has_rejection_candle=False,
        rejection_wick_ratio=0.0,
        vol_pullback_ratio=1.0,
        vol_rejection_ratio=1.0,
    )
    if len(candles) < 5 or atr <= 0 or vol_ma20 <= 0:
        return _empty

    # The rejection candle is candles[-1].  Scan the bars BEFORE it
    # (candles[-9:-1]) for the counter-trend bounce (rising closes in a
    # downtrend) that brought price back into the MA25 resistance zone.
    pre_last = candles[-9:-1]
    pre_closes = [float(c["close"]) for c in pre_last]
    pre_volumes = [float(c["volume"]) for c in pre_last]
    n_pre = len(pre_closes)
    pullback_candles = 0
    for i in range(n_pre - 1, max(0, n_pre - 7), -1):
        if i > 0 and pre_closes[i] > pre_closes[i - 1]:  # rising bounce
            pullback_candles += 1
        else:
            break

    last_close = float(candles[-1]["close"])
    # Pullback zone: price must be near MA25 from below (within pullback_zone_atr)
    distance_to_ma = ma25 - last_close
    has_pullback_ma25 = 0 <= distance_to_ma <= atr * pullback_zone_atr

    # Rejection candle: upper wick dominance + bearish close
    last_candle = candles[-1]
    wick_ratio = _upper_wick_ratio(last_candle)
    is_bearish_close = float(last_candle["close"]) < float(last_candle["open"])
    has_rejection_wick = wick_ratio >= min_rejection_wick and is_bearish_close

    # Alternate path: shallow MA7 reclaim that never reached the MA25 zone.
    cross_recovery = _ma7_cross_recovery(candles, "SHORT", ma25)
    has_pullback = has_pullback_ma25 or cross_recovery
    has_rejection = has_rejection_wick or cross_recovery

    # Volume ratios — compare pullback-bar avg volume to vol_ma20
    if pullback_candles > 0:
        pb_vols = pre_volumes[-pullback_candles:]
        vol_pullback_ratio = (sum(pb_vols) / len(pb_vols)) / vol_ma20 if pb_vols else 1.0
    else:
        vol_pullback_ratio = 1.0
    vol_rejection_ratio = float(candles[-1]["volume"]) / vol_ma20

    return EntryQualityResult(
        has_pullback=has_pullback,
        pullback_candles=pullback_candles,
        has_rejection_candle=has_rejection,
        rejection_wick_ratio=wick_ratio,
        vol_pullback_ratio=vol_pullback_ratio,
        vol_rejection_ratio=vol_rejection_ratio,
    )


def detect_long_entry_quality(
    candles: list[dict],
    atr: float,
    ma25: float,
    vol_ma20: float,
    pullback_zone_atr: float = 0.8,
    min_rejection_wick: float = 0.35,
) -> EntryQualityResult:
    """
    Mirror of ``detect_short_entry_quality`` for LONG setups.

    Pullback: price sits within ``pullback_zone_atr`` ATR above MA25 (support),
    OR satisfies the MA7 cross-recovery: previous candle red and closed on/below
    MA7 (the dip), current candle closed back above MA7 (the reclaim), with
    MA7/MA25 separated by at least ``MIN_MA_GAP_PCT`` to rule out a
    sideways/choppy market (see ``_ma7_cross_recovery``).
    Rejection: current candle has a bullish lower-wick hammer (lower wick ≥
    ``min_rejection_wick``) with a bullish close (close > open), OR satisfies
    the MA7 cross-recovery above.
    """
    _empty = EntryQualityResult(
        has_pullback=False,
        pullback_candles=0,
        has_rejection_candle=False,
        rejection_wick_ratio=0.0,
        vol_pullback_ratio=1.0,
        vol_rejection_ratio=1.0,
    )
    if len(candles) < 5 or atr <= 0 or vol_ma20 <= 0:
        return _empty

    # The rejection candle is candles[-1].  Scan the bars BEFORE it
    # (candles[-9:-1]) for the pullback (declining closes in an uptrend)
    # that brought price back into the MA25 support zone.
    pre_last = candles[-9:-1]
    pre_closes = [float(c["close"]) for c in pre_last]
    pre_volumes = [float(c["volume"]) for c in pre_last]
    n_pre = len(pre_closes)
    pullback_candles = 0
    for i in range(n_pre - 1, max(0, n_pre - 7), -1):
        if i > 0 and pre_closes[i] < pre_closes[i - 1]:  # falling into support
            pullback_candles += 1
        else:
            break

    last_close = float(candles[-1]["close"])
    distance_to_ma = last_close - ma25
    has_pullback_ma25 = 0 <= distance_to_ma <= atr * pullback_zone_atr

    last_candle = candles[-1]
    wick_ratio = _lower_wick_ratio(last_candle)
    is_bullish_close = float(last_candle["close"]) > float(last_candle["open"])
    has_rejection_wick = wick_ratio >= min_rejection_wick and is_bullish_close

    # Alternate path: shallow MA7 reclaim that never reached the MA25 zone.
    cross_recovery = _ma7_cross_recovery(candles, "LONG", ma25)
    has_pullback = has_pullback_ma25 or cross_recovery
    has_rejection = has_rejection_wick or cross_recovery

    if pullback_candles > 0:
        pb_vols = pre_volumes[-pullback_candles:]
        vol_pullback_ratio = (sum(pb_vols) / len(pb_vols)) / vol_ma20 if pb_vols else 1.0
    else:
        vol_pullback_ratio = 1.0
    vol_rejection_ratio = float(candles[-1]["volume"]) / vol_ma20

    return EntryQualityResult(
        has_pullback=has_pullback,
        pullback_candles=pullback_candles,
        has_rejection_candle=has_rejection,
        rejection_wick_ratio=wick_ratio,
        vol_pullback_ratio=vol_pullback_ratio,
        vol_rejection_ratio=vol_rejection_ratio,
    )


def calculate_oi_acceleration(
    oi_history: Sequence[float],
    window: int = 4,
) -> float:
    """
    Calculate the acceleration (second derivative) of Open Interest.

    A positive value means OI is growing *faster* — new positions are entering
    the market, providing fuel for further price movement.

    A negative value means the rate of OI growth is slowing (potential
    exhaustion of the current move — avoid entering).

    The result is normalised by the absolute value of the starting OI to make
    it comparable across assets with different absolute OI levels.

    Returns 0.0 when insufficient data is available.
    """
    values = [float(v) for v in oi_history if v is not None]
    if len(values) < window + 1 or values[0] == 0:
        return 0.0
    # First differences: periodic change in OI
    changes = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    recent = changes[-window:]
    if len(recent) < 2:
        return 0.0
    # Second difference normalised by |initial OI|
    return (recent[-1] - recent[0]) / abs(values[0])


@dataclass(frozen=True)
class IndicatorResult:
    candles: list[dict]
    price: float
    ma7: float
    ma25: float
    ma99: float
    delta: float
    cvd: float
    atr: float
    atr_ma20: float
    adx: float
    volume: float
    volume_ma20: float
    swing_high: float
    swing_low: float


def _wilder(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def calculate_indicators(candles: list[dict], period: int = 14) -> IndicatorResult:
    if len(candles) < 100:
        raise ValueError("At least 100 candles are required")

    frame = pd.DataFrame(candles).copy()
    numeric = ["open", "high", "low", "close", "volume", "taker_buy_volume"]
    frame[numeric] = frame[numeric].astype(float)

    frame["ma7"] = frame["close"].rolling(7).mean()
    frame["ma25"] = frame["close"].rolling(25).mean()
    frame["ma99"] = frame["close"].rolling(99).mean()
    frame["taker_sell_volume"] = frame["volume"] - frame["taker_buy_volume"]
    frame["delta"] = frame["taker_buy_volume"] - frame["taker_sell_volume"]
    frame["cvd"] = frame["delta"].cumsum()
    frame["volume_ma20"] = frame["volume"].rolling(20).mean()

    previous_close = frame["close"].shift(1)
    true_range = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    frame["atr"] = _wilder(true_range, period)
    frame["atr_ma20"] = frame["atr"].rolling(20).mean()

    up_move = frame["high"].diff()
    down_move = -frame["low"].diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0), index=frame.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0), index=frame.index)
    atr = _wilder(true_range, period)
    plus_di = 100 * _wilder(plus_dm, period) / atr.replace(0, np.nan)
    minus_di = 100 * _wilder(minus_dm, period) / atr.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    frame["adx"] = _wilder(dx, period).fillna(0)

    recent = frame.tail(20)
    row = frame.iloc[-1]
    enriched = frame.tail(120).replace({np.nan: None}).to_dict("records")
    return IndicatorResult(
        candles=enriched,
        price=float(row["close"]),
        ma7=float(row["ma7"]),
        ma25=float(row["ma25"]),
        ma99=float(row["ma99"]),
        delta=float(row["delta"]),
        cvd=float(row["cvd"]),
        atr=float(row["atr"]),
        atr_ma20=float(row["atr_ma20"]),
        adx=float(row["adx"]),
        volume=float(row["volume"]),
        volume_ma20=float(row["volume_ma20"]),
        swing_high=float(recent["high"].max()),
        swing_low=float(recent["low"].min()),
    )
