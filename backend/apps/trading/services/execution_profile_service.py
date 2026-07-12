from dataclasses import dataclass

from .indicator_service import IndicatorResult
from .signal_service import SignalResult


@dataclass(frozen=True)
class ExecutionProfile:
    regime: str
    regime_label: str
    regime_notes: list[str]
    confidence_score: int
    leverage_factor: float
    effective_leverage: int
    tp_r_multiple: float
    alignment_score: str


def _regime_from_context(
    config,
    signal: SignalResult,
    signal_indicators: IndicatorResult,
    trend_state,
    higher_trend_state,
) -> tuple[str, str, list[str]]:
    if not getattr(config, "auto_regime_enabled", True):
        return "MANUAL", "Manual", ["regime auto-adjustment is disabled"]

    aligned = (
        (signal.signal == "LONG" and "UPTREND" in higher_trend_state.value)
        or (signal.signal == "SHORT" and "DOWNTREND" in higher_trend_state.value)
    )
    notes: list[str] = []

    if signal_indicators.atr_ma20 > 0 and signal_indicators.atr >= signal_indicators.atr_ma20 * 1.35:
        notes.append("ATR is running hot versus ATR MA20")
    if signal_indicators.adx >= float(config.adx_min) * 1.35:
        notes.append("ADX is significantly above the minimum")
    if aligned:
        notes.append(f"{config.timeframe_trend} trend is aligned")
    if signal.trend_state.startswith("CONFIRMED"):
        notes.append("signal timeframe trend is confirmed")
    if signal.trend_state.startswith("EARLY"):
        notes.append("signal timeframe trend is early but aligned")
    if signal.trend_state.startswith("WEAK"):
        notes.append("signal timeframe trend is weakening")

    if signal_indicators.atr_ma20 > 0 and signal_indicators.atr >= signal_indicators.atr_ma20 * 1.5:
        return "HIGH_VOLATILITY", "High volatility", notes
    if aligned and signal.trend_state.startswith("CONFIRMED") and signal_indicators.adx >= float(config.adx_min) * 1.2:
        return "EXPANSION", "Trend expansion", notes
    if aligned and ("UPTREND" in signal.trend_state or "DOWNTREND" in signal.trend_state):
        return "TRENDING", "Trending", notes
    if signal.trend_state.startswith("WEAK"):
        return "PULLBACK", "Pullback", notes
    return "CHOPPY", "Choppy", notes or ["trend strength is mixed"]


def build_execution_profile(
    config,
    signal: SignalResult,
    signal_indicators: IndicatorResult,
    metrics: dict,
    trend_state,
    higher_trend_state,
) -> ExecutionProfile:
    preferred_score = (
        signal.long_score
        if signal.signal == "LONG"
        else signal.short_score
        if signal.signal == "SHORT"
        else max(signal.long_score, signal.short_score)
    )
    aligned = (
        (signal.signal == "LONG" and "UPTREND" in higher_trend_state.value)
        or (signal.signal == "SHORT" and "DOWNTREND" in higher_trend_state.value)
    )
    confidence = preferred_score
    if aligned:
        confidence += 8
    if signal_indicators.volume > signal_indicators.volume_ma20:
        confidence += 4
    if metrics.get("open_interest_change_available") and float(metrics.get("open_interest_change_percent", 0)) > 0:
        confidence += 5
    if signal.trend_state.startswith("CONFIRMED"):
        confidence += 6
    elif signal.trend_state.startswith("EARLY"):
        confidence += 2

    regime, regime_label, regime_notes = _regime_from_context(
        config,
        signal,
        signal_indicators,
        trend_state,
        higher_trend_state,
    )

    tp_factor = 1.0
    leverage_factor = 1.0
    # Confidence bands rescaled to the new 0-90 signal score + small bonuses
    # (aligned +8, volume +4, OI +5, trend +6 = max ~113 for a perfect setup).
    # Old bands were 115/100/90 for a 0-137 scale; new equivalent at ~80% gives
    # 92/80/72.  Values below 72 are weak / blocked setups.
    if confidence >= 92:
        tp_factor += 0.3
        leverage_factor = 1.0
    elif confidence >= 80:
        tp_factor += 0.15
        leverage_factor = 0.85
    elif confidence >= 72:
        tp_factor += 0.05
        leverage_factor = 0.7
    else:
        tp_factor -= 0.2
        leverage_factor = 0.55

    if regime == "EXPANSION":
        tp_factor += 0.25
    elif regime == "TRENDING":
        tp_factor += 0.1
    elif regime == "HIGH_VOLATILITY":
        tp_factor -= 0.25
        leverage_factor *= 0.75
    elif regime == "PULLBACK":
        tp_factor -= 0.1
        leverage_factor *= 0.8
    elif regime == "CHOPPY":
        tp_factor -= 0.35
        leverage_factor *= 0.65

    tp_r_multiple = max(1.2, min(float(config.atr_multiplier_tp) * tp_factor, 6.0))
    if not getattr(config, "confidence_leverage_enabled", True):
        effective_leverage = int(config.leverage)
        leverage_factor = 1.0
    else:
        effective_leverage = max(1, min(int(round(float(config.leverage) * leverage_factor)), int(config.leverage)))

    alignment_score = "aligned" if aligned else "counter"
    return ExecutionProfile(
        regime=regime,
        regime_label=regime_label,
        regime_notes=regime_notes,
        confidence_score=confidence,
        leverage_factor=leverage_factor,
        effective_leverage=effective_leverage,
        tp_r_multiple=tp_r_multiple,
        alignment_score=alignment_score,
    )
