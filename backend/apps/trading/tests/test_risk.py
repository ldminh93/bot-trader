import pytest

from apps.trading.services.risk_service import RiskLimitExceeded, calculate_risk_plan


def test_long_risk_plan_sizes_position_by_stop_distance():
    plan = calculate_risk_plan(
        side="LONG",
        entry_price=100,
        account_balance=10_000,
        risk_percent=1,
        atr=2,
        ma7=99,
        ma25=98,
        ma99=97,
    )
    assert plan.stop_loss == 98.5
    assert plan.risk_amount == 100
    assert plan.quantity == pytest.approx(66.66666667)
    assert plan.take_profit_1 == 101.5
    assert plan.take_profit_2 == 103.0
    assert plan.take_profit_3 == 104.5


def test_fixed_margin_sizes_short_position_using_leverage():
    plan = calculate_risk_plan(
        side="SHORT",
        entry_price=60_000,
        account_balance=10_000,
        risk_percent=1,
        atr=500,
        ma7=60_100,
        ma25=60_200,
        ma99=60_300,
        position_margin=30,
        leverage=10,
    )

    assert plan.stop_loss == 60_225
    assert plan.quantity == 0.005
    assert plan.quantity * 60_000 == 300
    assert plan.risk_amount == 1.125


def test_invalid_side_is_rejected():
    with pytest.raises(ValueError):
        calculate_risk_plan("FLAT", 100, 10_000, 1, 2, ma7=104, ma25=96)


def test_long_uses_nearest_ma_support_with_atr_buffer():
    """The nearest support *below* entry (highest of the qualifying MAs) is
    the tightest meaningful level — not the farthest one."""
    plan = calculate_risk_plan(
        "LONG",
        100,
        10_000,
        1,
        2,
        ma7=99.8,
        ma25=99,
        ma99=98.5,
        leverage=10,
        atr_buffer_multiplier=0.25,
    )

    assert plan.stop_loss == 99.3
    assert plan.risk_per_unit == pytest.approx(0.7)


def test_margin_loss_cap_rejects_entry_when_technical_stop_exceeds_it():
    """
    Reproduces the reported bug: a structurally-correct MA-support stop can
    still imply losing far more of the position margin than configured once
    leverage amplifies the price distance — e.g. a 7% price move at 5x
    leverage is a 35% margin loss, well above the default 20% cap. This must
    be documented in the Settings UI ("Skip entries when the technical stop
    would lose more than this percent of position margin") — before this
    fix, max_margin_loss_percent was accepted but never enforced.
    """
    with pytest.raises(RiskLimitExceeded, match="35.0%"):
        calculate_risk_plan(
            "LONG",
            100,
            10_000,
            1,
            atr=10,
            ma7=93,
            leverage=5,
            atr_buffer_multiplier=0,
        )


def test_margin_loss_cap_allows_entry_within_the_cap():
    """Same stop distance, lower leverage — margin loss now sits under the
    default 20% cap, so the entry proceeds."""
    plan = calculate_risk_plan(
        "LONG",
        100,
        10_000,
        1,
        atr=10,
        ma7=93,
        leverage=2,
        atr_buffer_multiplier=0,
    )

    assert plan.stop_loss == 93
    assert plan.risk_per_unit == 7


def test_margin_loss_cap_can_be_disabled():
    """max_margin_loss_percent=0 explicitly disables the check (documented in
    the Settings UI) even for a stop that would otherwise be rejected."""
    plan = calculate_risk_plan(
        "LONG",
        100,
        10_000,
        1,
        atr=10,
        ma7=93,
        leverage=5,
        atr_buffer_multiplier=0,
        max_margin_loss_percent=0,
    )

    assert plan.stop_loss == 93


def test_margin_loss_cap_respects_custom_value():
    """A wider custom cap (40%) allows the same 35%-margin-loss stop that the
    default 20% cap would reject."""
    plan = calculate_risk_plan(
        "LONG",
        100,
        10_000,
        1,
        atr=10,
        ma7=93,
        leverage=5,
        atr_buffer_multiplier=0,
        max_margin_loss_percent=40,
    )

    assert plan.stop_loss == 93


def test_forced_stop_loss_percent_overrides_ma_support_long():
    """MA-stack-reversal entries use a flat % stop instead of the nearest-MA one."""
    plan = calculate_risk_plan(
        side="LONG",
        entry_price=100,
        account_balance=10_000,
        risk_percent=1,
        atr=2,
        forced_stop_loss_percent=10.0,
        forced_take_profit_1=105.0,
        forced_take_profit_2=110.0,
    )
    assert plan.stop_loss == pytest.approx(90.0)
    assert plan.risk_per_unit == pytest.approx(10.0)
    assert plan.take_profit_1 == 105.0
    assert plan.take_profit_2 == 110.0
    assert plan.take_profit_3 == 110.0


def test_forced_stop_loss_percent_overrides_ma_support_short():
    plan = calculate_risk_plan(
        side="SHORT",
        entry_price=100,
        account_balance=10_000,
        risk_percent=1,
        atr=2,
        forced_stop_loss_percent=10.0,
        forced_take_profit_1=95.0,
        forced_take_profit_2=90.0,
    )
    assert plan.stop_loss == pytest.approx(110.0)
    assert plan.risk_per_unit == pytest.approx(10.0)
    assert plan.take_profit_1 == 95.0
    assert plan.take_profit_2 == 90.0


def test_forced_stop_loss_percent_ignores_atr_runaway_cap():
    """A flat % stop is allowed to exceed the normal 3x-ATR runaway-stop cap —
    that cap only guards against MAs lagging far behind price, not this path."""
    plan = calculate_risk_plan(
        side="LONG",
        entry_price=100,
        account_balance=10_000,
        risk_percent=1,
        atr=0.5,  # 3x ATR = 1.5, far tighter than the 10% (10-unit) forced stop
        forced_stop_loss_percent=10.0,
        forced_take_profit_1=105.0,
        forced_take_profit_2=110.0,
    )
    assert plan.stop_loss == pytest.approx(90.0)


def test_forced_stop_loss_percent_scales_by_leverage():
    """forced_stop_loss_percent is a margin-ROI target: at x4 leverage a 10%
    margin-ROI stop must sit only 2.5% away in price, not 10%."""
    plan = calculate_risk_plan(
        side="LONG",
        entry_price=100,
        account_balance=10_000,
        risk_percent=1,
        atr=2,
        leverage=4,
        forced_stop_loss_percent=10.0,
        forced_take_profit_1=105.0,
        forced_take_profit_2=110.0,
    )
    assert plan.stop_loss == pytest.approx(97.5)
    assert plan.risk_per_unit == pytest.approx(2.5)
