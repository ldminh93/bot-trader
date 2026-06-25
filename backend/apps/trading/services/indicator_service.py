from dataclasses import dataclass

import numpy as np
import pandas as pd


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
