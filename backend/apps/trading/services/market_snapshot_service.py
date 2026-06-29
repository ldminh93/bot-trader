import time
from dataclasses import dataclass, replace

from apps.trading.models import MarketSnapshot, TradingBotConfig

from .binance_service import BinanceService
from .execution_profile_service import build_execution_profile
from .indicator_service import IndicatorResult, calculate_indicators
from .opportunity_service import grade_from_context, opportunity_score
from .signal_service import SignalResult, score_signal
from .trend_service import detect_trend_state, explain_trend_state


@dataclass(frozen=True)
class MarketEvaluation:
    snapshot: MarketSnapshot
    indicators: IndicatorResult
    metrics: dict
    signal: SignalResult


def _tf_alignment_score(signal_side: str, signal_state, trend_state, bias_4h_state) -> int:
    """Score 0-3: how many timeframes (signal TF, trend TF, 4H) align with the signal direction."""
    if signal_side == "NO_TRADE":
        return 0
    score = 0
    if signal_side == "LONG" and "UPTREND" in signal_state.value:
        score += 1
    elif signal_side == "SHORT" and "DOWNTREND" in signal_state.value:
        score += 1
    if _alignment_matches(signal_side, trend_state):
        score += 1
    if bias_4h_state is not None and _alignment_matches(signal_side, bias_4h_state):
        score += 1
    return score


def _alignment_matches(signal_side: str, higher_trend_state) -> bool:
    if signal_side == "LONG":
        return "UPTREND" in higher_trend_state.value
    if signal_side == "SHORT":
        return "DOWNTREND" in higher_trend_state.value
    return True


def _setup_tags(
    signal: SignalResult,
    trend_state,
    higher_trend_state,
    metrics: dict,
    indicators: IndicatorResult,
    config: TradingBotConfig,
) -> list[str]:
    oi_change = float(metrics.get("open_interest_change_percent", 0))
    oi_state = (
        "unavailable"
        if not metrics.get("open_interest_change_available", False)
        else "increasing" if oi_change > 0 else "decreasing" if oi_change < 0 else "flat"
    )
    volume_state = "above_ma20" if indicators.volume > indicators.volume_ma20 else "below_ma20"
    alignment_state = "aligned" if _alignment_matches(signal.signal, higher_trend_state) else "counter"
    tags = [
        f"state:{trend_state.value.lower()}",
        f"higher:{higher_trend_state.value.lower()}",
        f"signal:{signal.signal.lower()}",
        f"alignment:{alignment_state}",
        f"oi:{oi_state}",
        f"volume:{volume_state}",
        f"threshold:{int(config.entry_score_threshold)}",
    ]
    return list(dict.fromkeys(tags))


def _oi_series(config: TradingBotConfig, metrics: dict) -> list[float]:
    current = float(metrics["open_interest"])
    history = list(
        MarketSnapshot.objects.filter(
            symbol=config.symbol,
            timeframe=config.timeframe_signal,
        )
        .order_by("-created_at")
        .values_list("open_interest", flat=True)[:4]
    )
    values = [float(value) for value in reversed(history)]
    if not values and metrics.get("open_interest_change_available") and current > 0:
        change = float(metrics["open_interest_change_percent"]) / 100
        previous = current / (1 + change) if 1 + change else current
        values.append(previous)
    values.append(current)
    return values


def evaluate_market_conditions(
    config: TradingBotConfig,
    signal_candles: list[dict],
    trend_candles: list[dict],
    metrics: dict,
    oi_series: list[float] | None = None,
    bias_candles: list[dict] | None = None,
) -> tuple[IndicatorResult, SignalResult, list[str], object, object, list[str], dict]:
    signal_indicators = calculate_indicators(signal_candles)
    trend_indicators = calculate_indicators(trend_candles)
    oi_values = oi_series or _oi_series(config, metrics)
    trend_state = detect_trend_state(
        signal_indicators,
        float(config.adx_min),
        oi_values,
    )
    higher_trend_state = detect_trend_state(
        trend_indicators,
        float(config.adx_min),
        oi_values,
    )
    bias_4h_state = None
    if bias_candles:
        bias_indicators = calculate_indicators(bias_candles)
        bias_4h_state = detect_trend_state(bias_indicators, float(config.adx_min), oi_values)
    signal = score_signal(
        signal_indicators,
        trend_state,
        metrics["open_interest_change_percent"],
        metrics["funding_rate"],
        metrics["top_ratio_direction"],
        config.enable_long,
        config.enable_short,
        int(config.entry_score_threshold),
        config.pullback_entry_enabled,
        float(config.max_entry_distance_atr),
    )
    trend_reasons = explain_trend_state(
        signal_indicators,
        float(config.adx_min),
        oi_values,
        trend_state,
    )

    if signal.signal != "NO_TRADE":
        extra_reasons: list[str] = []
        if config.require_trend_alignment and not _alignment_matches(signal.signal, higher_trend_state):
            extra_reasons.append(
                f"{signal.signal} requires {config.timeframe_trend} trend alignment"
            )
        if bias_4h_state is not None and not _alignment_matches(signal.signal, bias_4h_state):
            extra_reasons.append(
                f"{signal.signal} requires 4H trend alignment (4H state: {bias_4h_state.value})"
            )
        if config.require_open_interest_confirmation:
            if not metrics["open_interest_change_available"]:
                extra_reasons.append("open interest confirmation is unavailable")
            elif metrics["open_interest_change_percent"] <= 0:
                extra_reasons.append("open interest is not increasing")
        if config.require_volume_confirmation and signal_indicators.volume <= signal_indicators.volume_ma20:
            extra_reasons.append("volume is not above volume MA20")
        if extra_reasons:
            signal = replace(
                signal,
                signal="NO_TRADE",
                reasons=extra_reasons,
            )

    decision_reasons = signal.reasons
    if signal.signal == "NO_TRADE":
        decision_reasons = list(dict.fromkeys([*trend_reasons, *signal.reasons]))

    tags = _setup_tags(
        signal,
        trend_state,
        higher_trend_state,
        metrics,
        signal_indicators,
        config,
    )
    higher_trend_reasons = explain_trend_state(
        trend_indicators,
        float(config.adx_min),
        oi_values,
        higher_trend_state,
    )
    execution = build_execution_profile(
        config,
        signal,
        signal_indicators,
        metrics,
        trend_state,
        higher_trend_state,
    )
    context = {
        "trend_reasons": trend_reasons,
        "higher_trend_reasons": higher_trend_reasons,
        "execution": {
            "regime": execution.regime,
            "regime_label": execution.regime_label,
            "regime_notes": execution.regime_notes,
            "confidence_score": execution.confidence_score,
            "leverage_factor": execution.leverage_factor,
            "effective_leverage": execution.effective_leverage,
            "tp_r_multiple": execution.tp_r_multiple,
            "alignment_score": execution.alignment_score,
        },
        "alignment": execution.alignment_score,
    }
    context["trade_grade"] = grade_from_context(
        execution.confidence_score,
        execution.alignment_score,
        signal.signal,
        execution.regime,
    )
    context["trend_4h"] = bias_4h_state.value if bias_4h_state is not None else None
    context["tf_alignment_score"] = _tf_alignment_score(
        signal.signal, trend_state, higher_trend_state, bias_4h_state
    )
    return signal_indicators, signal, decision_reasons, trend_state, higher_trend_state, tags, context


def collect_market_snapshot(config: TradingBotConfig) -> MarketEvaluation:
    client = BinanceService()
    signal_candles = client.fetch_klines(config.symbol, config.timeframe_signal, limit=300)
    trend_candles = client.fetch_klines(config.symbol, config.timeframe_trend, limit=200)
    bias_candles = None
    if config.require_4h_alignment or config.min_tf_alignment_score > 0:
        bias_candles = client.fetch_klines(config.symbol, "4h", limit=100)
        if config.use_closed_candle_confirmation:
            bias_candles = _closed_candles(bias_candles)
    if config.use_closed_candle_confirmation:
        signal_candles = _closed_candles(signal_candles)
        trend_candles = _closed_candles(trend_candles)
    metrics = client.market_metrics(config.symbol, config.timeframe_signal)
    signal_indicators, signal, decision_reasons, trend_state, higher_trend_state, tags, context = evaluate_market_conditions(
        config,
        signal_candles,
        trend_candles,
        metrics,
        bias_candles=bias_candles,
    )
    snapshot = MarketSnapshot.objects.create(
        symbol=config.symbol,
        timeframe=config.timeframe_signal,
        price=metrics["price"],
        ma7=signal_indicators.ma7,
        ma25=signal_indicators.ma25,
        ma99=signal_indicators.ma99,
        delta=signal_indicators.delta,
        cvd=signal_indicators.cvd,
        open_interest=metrics["open_interest"],
        open_interest_change_percent=metrics["open_interest_change_percent"],
        funding_rate=metrics["funding_rate"],
        top_trader_account_ratio=metrics["top_trader_account_ratio"],
        top_trader_position_ratio=metrics["top_trader_position_ratio"],
        adx=signal_indicators.adx,
        atr=signal_indicators.atr,
        volume=signal_indicators.volume,
        volume_ma20=signal_indicators.volume_ma20,
        trend=trend_state.value,
        payload={
            "source": metrics.get("source", "unknown"),
            "trend_state": trend_state.value,
            "trend_1h": higher_trend_state.value,
            "trend_4h": context["trend_4h"],
            "signal": signal.signal,
            "long_score": signal.long_score,
            "short_score": signal.short_score,
            "risk_multiplier": signal.risk_multiplier,
            "reasons": decision_reasons,
            "trend_reasons": context["trend_reasons"],
            "higher_timeframe_bias": {
                "signal_state": trend_state.value,
                "higher_state": higher_trend_state.value,
                "alignment": context["alignment"],
                "reasons": context["higher_trend_reasons"],
            },
            "regime": context["execution"]["regime"],
            "regime_label": context["execution"]["regime_label"],
            "regime_notes": context["execution"]["regime_notes"],
            "confidence_score": context["execution"]["confidence_score"],
            "trade_grade": context["trade_grade"],
            "tf_alignment_score": context["tf_alignment_score"],
            "opportunity_score": opportunity_score(
                {
                    "signal": signal.signal,
                    "confidence_score": context["execution"]["confidence_score"],
                    "higher_timeframe_bias": {"alignment": context["alignment"]},
                    "regime": context["execution"]["regime"],
                }
            ),
            "effective_leverage": context["execution"]["effective_leverage"],
            "leverage_factor": context["execution"]["leverage_factor"],
            "tp_r_multiple": context["execution"]["tp_r_multiple"],
            "setup_tags": tags,
            "open_interest_change_available": metrics["open_interest_change_available"],
            "statistics_period": metrics["statistics_period"],
            "candles": signal_indicators.candles,
        },
    )
    return MarketEvaluation(snapshot, signal_indicators, metrics, signal)


def _closed_candles(candles: list[dict]) -> list[dict]:
    if not candles:
        return candles
    now_ms = int(time.time() * 1000)
    if int(candles[-1].get("close_timestamp", 0)) > now_ms:
        return candles[:-1]
    return candles
