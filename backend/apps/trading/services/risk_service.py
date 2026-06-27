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
    swing_high: float,
    swing_low: float,
    ma7: float | None = None,
    ma25: float | None = None,
    ma99: float | None = None,
    position_margin: float | None = None,
    leverage: int = 1,
    atr_buffer_multiplier: float = 0.25,
    take_profit_r_multiple: float = 3.0,
    max_margin_loss_percent: float = 20.0,
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
    moving_averages = [
        float(value)
        for value in (ma7, ma25, ma99)
        if value is not None and float(value) > 0
    ]
    if side == "LONG":
        supports = [value for value in moving_averages if value < entry_price]
        if not supports:
            raise RiskLimitExceeded("LONG entry has no moving-average support below price")
        stop_loss = min(supports) - atr * atr_buffer_multiplier
        risk_per_unit = entry_price - stop_loss
        direction = 1
    elif side == "SHORT":
        resistances = [value for value in moving_averages if value > entry_price]
        if not resistances:
            raise RiskLimitExceeded("SHORT entry has no moving-average resistance above price")
        stop_loss = max(resistances) + atr * atr_buffer_multiplier
        risk_per_unit = stop_loss - entry_price
        direction = -1
    else:
        raise ValueError("Side must be LONG or SHORT")
    if risk_per_unit <= 0:
        raise ValueError("Invalid stop loss relative to entry")
    # Keep the computed margin loss available for callers, but do not block the trade.
    # The bot can still decide to use the technical stop even when it is wide.
    if position_margin is not None:
        if position_margin <= 0 or leverage <= 0:
            raise ValueError("Position margin and leverage must be positive")
        quantity = position_margin * leverage / entry_price
        risk_amount = quantity * risk_per_unit
    else:
        risk_amount = account_balance * risk_percent / 100
        quantity = risk_amount / risk_per_unit
    return RiskPlan(
        quantity=quantity,
        stop_loss=stop_loss,
        take_profit_1=entry_price
        + direction * risk_per_unit * take_profit_r_multiple / 3,
        take_profit_2=entry_price
        + direction * risk_per_unit * take_profit_r_multiple * 2 / 3,
        take_profit_3=entry_price
        + direction * risk_per_unit * take_profit_r_multiple,
        risk_amount=risk_amount,
        risk_per_unit=risk_per_unit,
    )
