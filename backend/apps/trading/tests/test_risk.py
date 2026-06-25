import pytest

from apps.trading.services.risk_service import RiskLimitExceeded, calculate_risk_plan


def test_long_risk_plan_sizes_position_by_stop_distance():
    plan = calculate_risk_plan(
        side="LONG",
        entry_price=100,
        account_balance=10_000,
        risk_percent=1,
        atr=2,
        swing_high=104,
        swing_low=96,
        ma7=99,
        ma25=98,
        ma99=97,
    )
    assert plan.stop_loss == 96.5
    assert plan.risk_amount == 100
    assert plan.quantity == pytest.approx(28.57142857)
    assert plan.take_profit_1 == 103.5
    assert plan.take_profit_3 == 110.5


def test_fixed_margin_sizes_short_position_using_leverage():
    plan = calculate_risk_plan(
        side="SHORT",
        entry_price=60_000,
        account_balance=10_000,
        risk_percent=1,
        atr=500,
        swing_high=61_000,
        swing_low=59_000,
        ma7=60_100,
        ma25=60_200,
        ma99=60_300,
        position_margin=30,
        leverage=10,
    )

    assert plan.quantity == 0.005
    assert plan.quantity * 60_000 == 300
    assert plan.risk_amount == 2.125


def test_invalid_side_is_rejected():
    with pytest.raises(ValueError):
        calculate_risk_plan("FLAT", 100, 10_000, 1, 2, 104, 96)


def test_long_uses_lowest_ma_support_with_atr_buffer():
    plan = calculate_risk_plan(
        "LONG",
        100,
        10_000,
        1,
        2,
        104,
        96,
        ma7=99.8,
        ma25=99,
        ma99=98.5,
        leverage=10,
        atr_buffer_multiplier=0.25,
    )

    assert plan.stop_loss == 98
    assert plan.risk_per_unit == 2


def test_trade_is_skipped_when_ma_stop_exceeds_margin_loss_cap():
    with pytest.raises(
        RiskLimitExceeded,
        match="above the 20.0% cap",
    ):
        calculate_risk_plan(
            "LONG",
            100,
            10_000,
            1,
            2,
            104,
            96,
            ma7=99,
            ma25=95,
            ma99=90,
            leverage=10,
        )
