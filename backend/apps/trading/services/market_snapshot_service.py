from dataclasses import dataclass

from apps.trading.models import MarketSnapshot, TradingBotConfig

from .binance_service import BinanceService
from .indicator_service import IndicatorResult, calculate_indicators
from .signal_service import SignalResult, score_signal
from .trend_service import detect_trend_state, explain_trend_state


@dataclass(frozen=True)
class MarketEvaluation:
    snapshot: MarketSnapshot
    indicators: IndicatorResult
    metrics: dict
    signal: SignalResult


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


def collect_market_snapshot(config: TradingBotConfig) -> MarketEvaluation:
    client = BinanceService()
    signal_candles = client.fetch_klines(config.symbol, config.timeframe_signal)
    trend_candles = client.fetch_klines(config.symbol, config.timeframe_trend)
    metrics = client.market_metrics(config.symbol, config.timeframe_signal)
    signal_indicators = calculate_indicators(signal_candles)
    trend_indicators = calculate_indicators(trend_candles)
    oi_series = _oi_series(config, metrics)
    trend_state = detect_trend_state(
        signal_indicators,
        float(config.adx_min),
        oi_series,
    )
    higher_trend_state = detect_trend_state(
        trend_indicators,
        float(config.adx_min),
        oi_series,
    )
    signal = score_signal(
        signal_indicators,
        trend_state,
        metrics["open_interest_change_percent"],
        metrics["funding_rate"],
        metrics["top_ratio_direction"],
        config.enable_long,
        config.enable_short,
    )
    trend_reasons = explain_trend_state(
        signal_indicators,
        float(config.adx_min),
        oi_series,
        trend_state,
    )
    decision_reasons = signal.reasons
    if signal.signal == "NO_TRADE":
        decision_reasons = list(dict.fromkeys([*trend_reasons, *signal.reasons]))
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
            "signal": signal.signal,
            "long_score": signal.long_score,
            "short_score": signal.short_score,
            "risk_multiplier": signal.risk_multiplier,
            "reasons": decision_reasons,
            "trend_reasons": trend_reasons,
            "open_interest_change_available": metrics["open_interest_change_available"],
            "statistics_period": metrics["statistics_period"],
            "candles": signal_indicators.candles,
        },
    )
    return MarketEvaluation(snapshot, signal_indicators, metrics, signal)
