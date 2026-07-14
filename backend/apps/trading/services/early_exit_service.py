from dataclasses import dataclass
from datetime import datetime, timezone

from apps.trading.models import Trade, TradingBotConfig

from .binance_service import BinanceService
from .indicator_service import calculate_indicators
from .trend_service import TrendState, detect_trend_state


OPPOSITE_SCORE_CONDITION_THRESHOLD = 70
EXTREME_FUNDING_RATE = 0.001


@dataclass(frozen=True)
class EarlyExitDecision:
    should_close: bool
    conditions: list[str]

    @property
    def reason(self) -> str:
        joined = "; ".join(self.conditions)
        return f"Early exit ({len(self.conditions)} conditions): {joined}"


def _cvd_falling_persistently(candles: list) -> bool:
    """
    Require CVD to be declining on at least 2 consecutive candles (not just net decline).
    This filters out single-candle CVD dips that reverse quickly.
    """
    recent = [float(c["cvd"]) for c in candles[-6:]]
    if len(recent) < 3:
        return False
    # Need at least 2 consecutive declining steps in the last 5 transitions
    consecutive = 0
    for i in range(len(recent) - 1, 0, -1):
        if recent[i] < recent[i - 1]:
            consecutive += 1
            if consecutive >= 2:
                return True
        else:
            break
    return False


def _cvd_rising_persistently(candles: list) -> bool:
    recent = [float(c["cvd"]) for c in candles[-6:]]
    if len(recent) < 3:
        return False
    consecutive = 0
    for i in range(len(recent) - 1, 0, -1):
        if recent[i] > recent[i - 1]:
            consecutive += 1
            if consecutive >= 2:
                return True
        else:
            break
    return False


def _oi_series_for_early_exit(metrics: dict) -> list[float]:
    """Reconstruct a minimal 2-point OI series from the current snapshot + its % change."""
    current = float(metrics.get("open_interest", 0) or 0)
    if metrics.get("open_interest_change_available") and current > 0:
        change = float(metrics["open_interest_change_percent"]) / 100
        previous = current / (1 + change) if 1 + change else current
        return [previous, current]
    return [current]


def evaluate_early_exit(
    trade: Trade,
    config: TradingBotConfig,
    long_score: int,
    short_score: int,
) -> EarlyExitDecision:
    client = BinanceService()
    candles = client.fetch_klines(trade.symbol, "15m", limit=150)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    closed_candles = [
        candle
        for candle in candles
        if int(candle.get("close_timestamp", 0)) <= now_ms
    ]
    if len(closed_candles) < 100:
        return EarlyExitDecision(False, [])

    opened_at = getattr(trade, "opened_at", None)
    if opened_at is not None:
        opened_at_ms = int(opened_at.timestamp() * 1000)
        latest_closed_timestamp = max(
            int(candle.get("close_timestamp", 0)) for candle in closed_candles
        )
        if latest_closed_timestamp <= opened_at_ms:
            return EarlyExitDecision(False, [])

        # Grace period: wait until N 15m candles have closed since entry
        grace = int(config.early_exit_grace_candles) if hasattr(config, "early_exit_grace_candles") else 2
        if grace > 0:
            candles_since_entry = sum(
                1 for c in closed_candles
                if int(c.get("close_timestamp", 0)) > opened_at_ms
            )
            if candles_since_entry < grace:
                return EarlyExitDecision(False, [])

    adx_period = int(config.adx_period) if hasattr(config, "adx_period") else 14
    indicators = calculate_indicators(closed_candles, period=adx_period)
    metrics = client.market_metrics(trade.symbol, "15m")
    recent = indicators.candles[-4:]
    recent_deltas = [float(candle["delta"]) for candle in recent[-3:]]
    price_decreasing = float(recent[-1]["close"]) < float(recent[-2]["close"])
    price_increasing = float(recent[-1]["close"]) > float(recent[-2]["close"])
    oi_decreasing = (
        metrics["open_interest_change_available"]
        and metrics["open_interest_change_percent"] < 0
    )
    trend_state = detect_trend_state(
        indicators, float(config.adx_min), _oi_series_for_early_exit(metrics)
    )
    conditions: list[str] = []

    if trade.side == Trade.Side.LONG:
        if indicators.price < indicators.ma25:
            conditions.append("15m close is below MA25")
        if all(delta < 0 for delta in recent_deltas):
            conditions.append("last 3 candle deltas are negative")
        if _cvd_falling_persistently(indicators.candles):
            conditions.append("CVD falling for 2+ consecutive candles")
        if oi_decreasing and price_decreasing:
            conditions.append("open interest and price are decreasing")
        if indicators.adx < float(config.adx_min):
            conditions.append(f"15m ADX is below {float(config.adx_min):.1f}")
        if short_score >= OPPOSITE_SCORE_CONDITION_THRESHOLD:
            conditions.append(
                f"SHORT score is at least {OPPOSITE_SCORE_CONDITION_THRESHOLD}"
            )
        if metrics["funding_rate"] > EXTREME_FUNDING_RATE:
            conditions.append("funding is above +0.10%")
        if trend_state in {TrendState.CONFIRMED_DOWNTREND, TrendState.EARLY_DOWNTREND}:
            conditions.append(f"15m trend flipped to {trend_state.value.replace('_', ' ').lower()}")
    else:
        if indicators.price > indicators.ma25:
            conditions.append("15m close is above MA25")
        if all(delta > 0 for delta in recent_deltas):
            conditions.append("last 3 candle deltas are positive")
        if _cvd_rising_persistently(indicators.candles):
            conditions.append("CVD rising for 2+ consecutive candles")
        if oi_decreasing and price_increasing:
            conditions.append("open interest is decreasing while price increases")
        if indicators.adx < float(config.adx_min):
            conditions.append(f"15m ADX is below {float(config.adx_min):.1f}")
        if long_score >= OPPOSITE_SCORE_CONDITION_THRESHOLD:
            conditions.append(
                f"LONG score is at least {OPPOSITE_SCORE_CONDITION_THRESHOLD}"
            )
        if metrics["funding_rate"] < -EXTREME_FUNDING_RATE:
            conditions.append("funding is below -0.10%")
        if trend_state in {TrendState.CONFIRMED_UPTREND, TrendState.EARLY_UPTREND}:
            conditions.append(f"15m trend flipped to {trend_state.value.replace('_', ' ').lower()}")

    # Configurable threshold (default 3, was hardcoded 2)
    min_conditions = int(config.early_exit_min_conditions) if hasattr(config, "early_exit_min_conditions") else 3

    # Minimum loss guard: suppress early exit until the trade has lost enough
    # (prevents noise exits on tiny adverse moves near entry)
    min_loss_pct = float(getattr(config, "early_exit_min_loss_percent", 0) or 0)
    if min_loss_pct > 0:
        unrealized = float(getattr(trade, "unrealized_pnl", 0) or 0)
        if unrealized < 0:
            entry = float(trade.entry_price)
            qty = float(trade.quantity)
            lev = int(trade.leverage) or 1
            margin = entry * qty / lev
            margin_roi_pct = (unrealized / margin * 100) if margin else 0.0
            if margin_roi_pct > -min_loss_pct:
                return EarlyExitDecision(False, [])

    # Profit guard: if the trade is currently in profit, require one extra condition
    # to avoid closing winners on short-term noise
    effective_min = min_conditions
    if float(getattr(trade, "unrealized_pnl", 0) or 0) > 0:
        effective_min += 1

    return EarlyExitDecision(
        len(conditions) >= effective_min,
        conditions,
    )


def opposite_entry_has_new_candle_confirmation(
    user,
    symbol: str,
    candidate_side: str,
    signal_candles: list[dict],
) -> bool:
    last_early_exit = (
        Trade.objects.filter(
            user=user,
            symbol=symbol,
            status=Trade.Status.CLOSED,
            close_reason__startswith="Early exit",
        )
        .order_by("-closed_at")
        .first()
    )
    if (
        not last_early_exit
        or not last_early_exit.closed_at
        or candidate_side == last_early_exit.side
    ):
        return True

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    latest_closed_timestamp = max(
        (
            int(candle.get("close_timestamp", 0))
            for candle in signal_candles
            if int(candle.get("close_timestamp", 0)) <= now_ms
        ),
        default=0,
    )
    return latest_closed_timestamp > int(last_early_exit.closed_at.timestamp() * 1000)
