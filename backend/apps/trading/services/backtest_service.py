from dataclasses import dataclass
from decimal import Decimal

from .binance_service import BinanceService
from .market_snapshot_service import evaluate_market_conditions
from .risk_service import RiskLimitExceeded, calculate_risk_plan


@dataclass
class SimTrade:
    side: str
    entry_price: Decimal
    quantity: Decimal
    remaining_quantity: Decimal
    leverage: int
    stop_loss: Decimal
    take_profit_1: Decimal
    take_profit_2: Decimal
    take_profit_3: Decimal
    realized_pnl: Decimal
    fees: Decimal
    tp1_hit: bool
    tp2_hit: bool
    breakeven_moved: bool
    opened_at_ms: int
    setup_tags: list[str]
    open_reason: str


TAKER_FEE_RATE = Decimal("0.0005")


def _tf_minutes(value: str) -> int:
    mapping = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240}
    return mapping[value]


def _period_for_oi(signal_timeframe: str) -> str:
    return {"1m": "5m", "3m": "5m", "4h": "1h"}.get(signal_timeframe, signal_timeframe)


def _partial_close(trade: SimTrade, price: Decimal, fraction_of_original: Decimal) -> None:
    requested = trade.quantity * fraction_of_original
    closing_quantity = min(trade.remaining_quantity, requested)
    if closing_quantity <= 0:
        return
    direction = Decimal("1") if trade.side == "LONG" else Decimal("-1")
    gross = (price - trade.entry_price) * closing_quantity * direction
    fee = price * closing_quantity * TAKER_FEE_RATE
    trade.realized_pnl += gross - fee
    trade.fees += fee
    trade.remaining_quantity -= closing_quantity


def _update_trade(trade: SimTrade, current_price: Decimal, atr: float, trailing_multiplier: float) -> str | None:
    one_r = abs(trade.entry_price - trade.stop_loss)
    if not trade.breakeven_moved and (
        (trade.side == "LONG" and current_price >= trade.entry_price + one_r)
        or (trade.side == "SHORT" and current_price <= trade.entry_price - one_r)
    ):
        trade.stop_loss = trade.entry_price
        trade.breakeven_moved = True

    if not trade.tp1_hit and (
        (trade.side == "LONG" and current_price >= trade.take_profit_1)
        or (trade.side == "SHORT" and current_price <= trade.take_profit_1)
    ):
        _partial_close(trade, current_price, Decimal("0.30"))
        trade.tp1_hit = True
    if not trade.tp2_hit and (
        (trade.side == "LONG" and current_price >= trade.take_profit_2)
        or (trade.side == "SHORT" and current_price <= trade.take_profit_2)
    ):
        _partial_close(trade, current_price, Decimal("0.40"))
        trade.tp2_hit = True

    trail_distance = Decimal(str(atr)) * Decimal(str(trailing_multiplier))
    if trade.tp1_hit and trail_distance > 0:
        if trade.side == "LONG":
            trade.stop_loss = max(trade.stop_loss, current_price - trail_distance)
        else:
            trade.stop_loss = min(trade.stop_loss, current_price + trail_distance)

    stop_hit = (
        trade.side == "LONG" and current_price <= trade.stop_loss
    ) or (
        trade.side == "SHORT" and current_price >= trade.stop_loss
    )
    tp3_hit = (
        trade.side == "LONG" and current_price >= trade.take_profit_3
    ) or (
        trade.side == "SHORT" and current_price <= trade.take_profit_3
    )
    if stop_hit:
        _partial_close(trade, current_price, Decimal("1"))
        return "Stop loss or trailing stop"
    if tp3_hit:
        _partial_close(trade, current_price, Decimal("1"))
        return "Take profit 3"
    return None


def _early_exit_reason(trade: SimTrade, indicators, metrics: dict, config, long_score: int, short_score: int) -> str | None:
    recent = indicators.candles[-4:]
    recent_deltas = [float(candle["delta"]) for candle in recent[-3:]]
    recent_cvds = [float(candle["cvd"]) for candle in recent]
    price_decreasing = float(recent[-1]["close"]) < float(recent[-2]["close"])
    price_increasing = float(recent[-1]["close"]) > float(recent[-2]["close"])
    oi_decreasing = (
        metrics["open_interest_change_available"]
        and metrics["open_interest_change_percent"] < 0
    )
    conditions: list[str] = []
    if trade.side == "LONG":
        if indicators.price < indicators.ma25:
            conditions.append("15m close is below MA25")
        if all(delta < 0 for delta in recent_deltas):
            conditions.append("last 3 candle deltas are negative")
        if recent_cvds[-1] < recent_cvds[0]:
            conditions.append("CVD is falling")
        if oi_decreasing and price_decreasing:
            conditions.append("open interest and price are decreasing")
        if indicators.adx < float(config.adx_min):
            conditions.append(f"15m ADX is below {float(config.adx_min):.1f}")
        if short_score >= 80:
            conditions.append("SHORT score is at least 80")
    else:
        if indicators.price > indicators.ma25:
            conditions.append("15m close is above MA25")
        if all(delta > 0 for delta in recent_deltas):
            conditions.append("last 3 candle deltas are positive")
        if recent_cvds[-1] > recent_cvds[0]:
            conditions.append("CVD is rising")
        if oi_decreasing and price_increasing:
            conditions.append("open interest is decreasing while price increases")
        if indicators.adx < float(config.adx_min):
            conditions.append(f"15m ADX is below {float(config.adx_min):.1f}")
        if long_score >= 80:
            conditions.append("LONG score is at least 80")
    if len(conditions) >= 3:
        return f"Early exit ({len(conditions)} conditions): {'; '.join(conditions)}"
    return None


def run_backtest(config, limit: int = 320) -> dict:
    client = BinanceService()
    signal_candles = client.fetch_klines(config.symbol, config.timeframe_signal, limit=limit)
    trend_candles = client.fetch_klines(config.symbol, config.timeframe_trend, limit=max(150, limit // 4 + 120))
    oi_history = client.open_interest_history(config.symbol, _period_for_oi(config.timeframe_signal), limit=limit)
    if len(signal_candles) < 140 or len(trend_candles) < 100:
        return {"summary": {"trades": 0, "win_rate": 0, "realized_pnl": 0, "total_profit": 0}, "trades": []}

    account_balance = float(config.paper_balance)
    current_trade: SimTrade | None = None
    closed_trades: list[dict] = []

    for index in range(120, len(signal_candles)):
        signal_slice = signal_candles[: index + 1]
        current_ts = int(signal_slice[-1]["close_timestamp"])
        trend_slice = [
            candle for candle in trend_candles
            if int(candle["close_timestamp"]) <= current_ts
        ]
        if len(trend_slice) < 100:
            continue
        oi_slice = [item["open_interest"] for item in oi_history if item["timestamp"] <= current_ts][-5:]
        current_oi = oi_slice[-1] if oi_slice else 0.0
        oi_change = 0.0
        oi_available = len(oi_slice) >= 2 and oi_slice[-2] != 0
        if oi_available:
            oi_change = (current_oi - oi_slice[-2]) / oi_slice[-2] * 100
        metrics = {
            "price": float(signal_slice[-1]["close"]),
            "funding_rate": 0.0,
            "open_interest": current_oi,
            "open_interest_change_percent": oi_change,
            "open_interest_change_available": oi_available,
            "statistics_period": _period_for_oi(config.timeframe_signal),
            "top_trader_account_ratio": 1.0,
            "top_trader_position_ratio": 1.0,
            "top_ratio_direction": 0.0,
            "source": "backtest",
        }
        indicators, signal, _reasons, _trend_state, _higher_state, tags, context = evaluate_market_conditions(
            config,
            signal_slice,
            trend_slice,
            metrics,
            oi_series=oi_slice or [current_oi],
        )
        current_price = Decimal(str(metrics["price"]))

        if current_trade is not None:
            exit_reason = _update_trade(
                current_trade,
                current_price,
                indicators.atr,
                float(config.trailing_atr_multiplier) if config.use_trailing_stop else 0,
            )
            if exit_reason is None and current_ts > current_trade.opened_at_ms:
                exit_reason = _early_exit_reason(
                    current_trade,
                    indicators,
                    metrics,
                    config,
                    signal.long_score,
                    signal.short_score,
                )
                if exit_reason:
                    _partial_close(current_trade, current_price, Decimal("1"))
            if exit_reason:
                margin_basis = (
                    current_trade.entry_price * current_trade.quantity / Decimal(current_trade.leverage)
                    if current_trade.leverage > 0 else Decimal("0")
                )
                pnl_percent = float(current_trade.realized_pnl / margin_basis * 100) if margin_basis else 0
                closed_trades.append(
                    {
                        "side": current_trade.side,
                        "entry_price": float(current_trade.entry_price),
                        "exit_price": float(current_price),
                        "realized_pnl": float(current_trade.realized_pnl),
                        "pnl_percent": pnl_percent,
                        "opened_at_ms": current_trade.opened_at_ms,
                        "closed_at_ms": current_ts,
                        "close_reason": exit_reason,
                        "setup_tags": current_trade.setup_tags,
                    }
                )
                account_balance += float(current_trade.realized_pnl)
                current_trade = None

        if current_trade is not None or signal.signal == "NO_TRADE":
            continue

        position_margin = (
            float(config.position_margin_usdt) * signal.risk_multiplier
            if config.position_margin_usdt is not None
            else None
        )
        execution = context["execution"]
        try:
            plan = calculate_risk_plan(
                signal.signal,
                float(current_price),
                account_balance,
                float(config.risk_per_trade_percent) * signal.risk_multiplier,
                indicators.atr,
                indicators.swing_high,
                indicators.swing_low,
                indicators.ma7,
                indicators.ma25,
                indicators.ma99,
                position_margin,
                int(execution["effective_leverage"]),
                float(config.atr_multiplier_sl),
                float(execution["tp_r_multiple"]),
                float(config.max_margin_loss_percent),
            )
        except (RiskLimitExceeded, ValueError):
            continue
        quantity = Decimal(str(plan.quantity))
        fee = current_price * quantity * TAKER_FEE_RATE
        current_trade = SimTrade(
            side=signal.signal,
            entry_price=current_price,
            quantity=quantity,
            remaining_quantity=quantity,
            leverage=int(execution["effective_leverage"]),
            stop_loss=Decimal(str(plan.stop_loss)),
            take_profit_1=Decimal(str(plan.take_profit_1)),
            take_profit_2=Decimal(str(plan.take_profit_2)),
            take_profit_3=Decimal(str(plan.take_profit_3)),
            realized_pnl=-fee,
            fees=fee,
            tp1_hit=False,
            tp2_hit=False,
            breakeven_moved=False,
            opened_at_ms=current_ts,
            setup_tags=tags + [f"regime:{execution['regime'].lower()}", f"confidence:{execution['confidence_score']}"],
            open_reason=", ".join(signal.reasons),
        )

    wins = sum(1 for trade in closed_trades if trade["realized_pnl"] > 0)
    total_profit = sum(trade["realized_pnl"] for trade in closed_trades)
    return {
        "summary": {
            "trades": len(closed_trades),
            "win_rate": (wins / len(closed_trades) * 100) if closed_trades else 0,
            "realized_pnl": total_profit,
            "total_profit": total_profit,
        },
        "trades": closed_trades[-25:],
    }
