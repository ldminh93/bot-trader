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
    Price must be sitting within ``pullback_zone_atr`` ATR below MA25.
    This prevents chasing price after it has already fallen far from
    resistance — a primary cause of poor entry R:R.

    Rejection candle (primary entry trigger)
    ----------------------------------------
    The current candle must show a bearish upper-wick rejection (upper wick
    ≥ ``min_rejection_wick`` of the total range) *and* a bearish close
    (close < open).  This confirms that sellers are defending MA25.

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
    has_pullback = 0 <= distance_to_ma <= atr * pullback_zone_atr

    # Rejection candle: upper wick dominance + bearish close
    last_candle = candles[-1]
    wick_ratio = _upper_wick_ratio(last_candle)
    is_bearish_close = float(last_candle["close"]) < float(last_candle["open"])
    has_rejection = wick_ratio >= min_rejection_wick and is_bearish_close

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

    Pullback: price sits within ``pullback_zone_atr`` ATR above MA25 (support).
    Rejection: current candle has a bullish lower-wick hammer (lower wick ≥
    ``min_rejection_wick``) with a bullish close (close > open).
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
    has_pullback = 0 <= distance_to_ma <= atr * pullback_zone_atr

    last_candle = candles[-1]
    wick_ratio = _lower_wick_ratio(last_candle)
    is_bullish_close = float(last_candle["close"]) > float(last_candle["open"])
    has_rejection = wick_ratio >= min_rejection_wick and is_bullish_close

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
