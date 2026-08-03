from dataclasses import dataclass


class RiskLimitExceeded(ValueError):
    pass


@dataclass(frozen=True)
class RiskPlan:
    quantity: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    take_profit_3: float
    risk_amount: float
    risk_per_unit: float


def calculate_risk_plan(
    side: str,
    entry_price: float,
    account_balance: float,
    risk_percent: float,
    atr: float,
    ma7: float | None = None,
    ma25: float | None = None,
    ma99: float | None = None,
    position_margin: float | None = None,
    leverage: int = 1,
    atr_buffer_multiplier: float = 0.25,
    take_profit_r_multiple: float = 3.0,
    max_margin_loss_percent: float = 20.0,
    forced_stop_loss_percent: float | None = None,
    forced_take_profit_1: float | None = None,
    forced_take_profit_2: float | None = None,
) -> RiskPlan:
    if (
        account_balance <= 0
        or risk_percent <= 0
        or atr <= 0
        or leverage <= 0
        or atr_buffer_multiplier < 0
        or take_profit_r_multiple <= 0
        or max_margin_loss_percent < 0
    ):
        raise ValueError("Risk-plan inputs must be positive")
    if side not in {"LONG", "SHORT"}:
        raise ValueError("Side must be LONG or SHORT")
    direction = 1 if side == "LONG" else -1

    if forced_stop_loss_percent is not None:
        # Used for entries whose gate (e.g. detect_ma_stack_reversal) fires
        # independently of the MA-support structure this function otherwise
        # relies on — there's no "nearest MA" to anchor a stop to, so use a
        # flat % instead.  The 3x-ATR runaway-stop cap below doesn't apply
        # here since a flat % stop is the point, not a symptom of MAs lagging
        # far behind price.
        # forced_stop_loss_percent is a margin-ROI target, not a price-move %
        # — divide by leverage so e.g. 10% margin ROI at x4 leverage maps to
        # a 2.5% price move, not a 10% one.
        if forced_stop_loss_percent <= 0:
            raise ValueError("forced_stop_loss_percent must be positive")
        price_move_percent = forced_stop_loss_percent / leverage
        stop_loss = entry_price * (1 - direction * price_move_percent / 100)
        risk_per_unit = direction * (entry_price - stop_loss)
    else:
        moving_averages = [
            float(value)
            for value in (ma7, ma25, ma99)
            if value is not None and float(value) > 0
        ]
        if side == "LONG":
            supports = [value for value in moving_averages if value < entry_price]
            if not supports:
                raise RiskLimitExceeded("LONG entry has no moving-average support below price")
            # Nearest MA below entry = tightest meaningful support level
            stop_loss = max(supports) - atr * atr_buffer_multiplier
            risk_per_unit = entry_price - stop_loss
        else:
            resistances = [value for value in moving_averages if value > entry_price]
            if not resistances:
                raise RiskLimitExceeded("SHORT entry has no moving-average resistance above price")
            # Nearest MA above entry = tightest meaningful resistance level
            stop_loss = min(resistances) + atr * atr_buffer_multiplier
            risk_per_unit = stop_loss - entry_price
        if risk_per_unit <= 0:
            raise ValueError("Invalid stop loss relative to entry")
        # Hard cap: SL must not be more than 3× ATR away from entry regardless of MA distance.
        # This prevents runaway stops on volatile coins where MAs have lagged far behind price.
        max_risk_per_unit = atr * 3.0
        if risk_per_unit > max_risk_per_unit:
            raise RiskLimitExceeded(
                f"SL is {risk_per_unit / atr:.1f}× ATR from entry (max 3×) — "
                f"nearest MA is too far away; wait for a closer pullback"
            )

    if position_margin is not None:
        if position_margin <= 0 or leverage <= 0:
            raise ValueError("Position margin and leverage must be positive")
        quantity = position_margin * leverage / entry_price
        risk_amount = quantity * risk_per_unit
    else:
        risk_amount = account_balance * risk_percent / 100
        quantity = risk_amount / risk_per_unit

    if forced_take_profit_1 is not None and forced_take_profit_2 is not None:
        # Forced MA-based targets — no third stage beyond clearing the top MA.
        take_profit_1 = forced_take_profit_1
        take_profit_2 = forced_take_profit_2
        take_profit_3 = forced_take_profit_2
    else:
        take_profit_1 = entry_price + direction * risk_per_unit * take_profit_r_multiple / 3
        take_profit_2 = entry_price + direction * risk_per_unit * take_profit_r_multiple * 2 / 3
        take_profit_3 = entry_price + direction * risk_per_unit * take_profit_r_multiple

    return RiskPlan(
        quantity=quantity,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        take_profit_3=take_profit_3,
        risk_amount=risk_amount,
        risk_per_unit=risk_per_unit,
    )
