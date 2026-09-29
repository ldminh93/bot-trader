from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading.models import SignalDecision, Trade
from apps.trading.services.diagnostics_service import build_diagnostics


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("d@example.com", password="pw", is_staff=True)


def _window():
    today = timezone.localdate()
    return today - timedelta(days=7), today


def _decision(user, gate, hit, *, price=100, stop=97, tp1=103, window="outcome_4h", status="resolved", **kw):
    fields = dict(
        user=user, symbol="BTCUSDT", side="LONG", result=gate, price=price,
        ref_stop=stop, ref_tp1=tp1, levels_source="default",
        signal_candle_ts=SignalDecision.objects.count() + 1,
    )
    fields.update(kw)
    d = SignalDecision.objects.create(**fields)
    setattr(d, window, {"status": status, "first_hit": hit})
    d.save()
    return d


def _trade(user, pnl, *, r=None, mfe_r=None, mae_r=None, tags=None, regime="TRENDING", side="LONG",
           confidence=72, grade="B", reason="take profit", is_paper=True, closed_at=None, **kw):
    t = Trade.objects.create(
        user=user, symbol="BTCUSDT", side=side, status=Trade.Status.CLOSED, entry_price=100,
        quantity=1, stop_loss=95, initial_stop_loss=95, take_profit_1=105, take_profit_2=110,
        take_profit_3=115, open_reason="x", realized_pnl=Decimal(str(pnl)), is_paper=is_paper,
        close_reason=reason, setup_tags=tags or ["pullback"],
        replay_payload={"confidence_score": confidence, "trade_grade": grade, "regime": regime},
        closed_at=closed_at or timezone.now(),
        **kw,
    )
    Trade.objects.filter(pk=t.pk).update(
        r_multiple=None if r is None else Decimal(str(r)),
        mfe_r=None if mfe_r is None else Decimal(str(mfe_r)),
        mae_r=None if mae_r is None else Decimal(str(mae_r)),
    )
    return t


@pytest.mark.django_db
def test_gate_value_counts_wins_losses_and_net_r(user):
    for _ in range(3):
        _decision(user, "extended_move", "sl")        # 3 losses avoided -> +3R
    _decision(user, "extended_move", "tp1")           # 1 win missed (reward==risk) -> -1R
    _decision(user, "extended_move", "ambiguous")
    _decision(user, "extended_move", "none", status="pending")   # unresolved

    start, end = _window()
    gate = build_diagnostics(user, start, end)["gates"][0]

    assert gate["gate"] == "extended_move" and gate["blocked"] == 6 and gate["resolved"] == 5
    assert gate["would_lose_pct"] == 60.0 and gate["would_win_pct"] == 20.0 and gate["undecided_pct"] == 20.0
    assert gate["net_r"] == 2.0
    assert gate["low_sample"] is True


@pytest.mark.django_db
def test_gate_win_missed_uses_reward_to_risk(user):
    _decision(user, "funding", "tp1", stop=98, tp1=104)   # reward 4 / risk 2 = 2R missed
    start, end = _window()
    assert build_diagnostics(user, start, end)["gates"][0]["net_r"] == -2.0


@pytest.mark.django_db
def test_taken_decisions_are_not_gates_and_window_selects_outcome(user):
    _decision(user, "taken", "tp1")
    _decision(user, "funding", "sl", window="outcome_1h")
    start, end = _window()
    assert [g["gate"] for g in build_diagnostics(user, start, end)["gates"]] == ["funding"]
    # the 1h view sees the outcome, the default 4h view has nothing resolved for it
    assert build_diagnostics(user, start, end, window="4h")["gates"][0]["resolved"] == 0
    assert build_diagnostics(user, start, end, window="1h")["gates"][0]["resolved"] == 1


@pytest.mark.django_db
def test_calibration_buckets_and_grades(user):
    _trade(user, 10, r=1.0, confidence=72, grade="A")
    _trade(user, -5, r=-1.0, confidence=78, grade="A")
    _trade(user, 5, r=0.5, confidence=55, grade="C")
    start, end = _window()
    cal = build_diagnostics(user, start, end)["calibration"]

    buckets = {r["label"]: r for r in cal["by_score_bucket"]}
    assert buckets["70-79"]["trades"] == 2 and buckets["70-79"]["win_rate"] == 50.0
    assert buckets["70-79"]["avg_r"] == 0.0 and buckets["50-59"]["avg_r"] == 0.5
    grades = {r["label"]: r for r in cal["by_grade"]}
    assert grades["A"]["trades"] == 2 and grades["C"]["trades"] == 1
    assert all(r["low_sample"] for r in cal["by_grade"])


@pytest.mark.django_db
def test_low_sample_flag_clears_at_thirty(user):
    for _ in range(30):
        _trade(user, 1, r=0.2)
    start, end = _window()
    row = build_diagnostics(user, start, end)["expectancy"]["by_tag"][0]
    assert row["label"] == "pullback" and row["trades"] == 30 and row["low_sample"] is False


@pytest.mark.django_db
def test_expectancy_by_tag_and_regime_side_ignores_structural_tags(user):
    _trade(user, 5, r=0.5, tags=["pullback", "grade:B", "confidence:72", "regime:trending"], regime="TRENDING", side="SHORT")
    start, end = _window()
    exp = build_diagnostics(user, start, end)["expectancy"]
    assert [r["label"] for r in exp["by_tag"]] == ["pullback"]
    assert exp["by_regime_side"][0]["label"] == "TRENDING / SHORT"
    assert exp["by_regime_side"][0]["expectancy_r"] == 0.5


@pytest.mark.django_db
def test_unavailable_r_is_null_not_zero(user):
    _trade(user, 5, r=None)
    Trade.objects.update(initial_stop_loss=None)   # legacy trade: no initial risk on record
    start, end = _window()
    row = build_diagnostics(user, start, end)["calibration"]["by_grade"][0]
    assert row["avg_r"] is None and row["win_rate"] == 100.0


@pytest.mark.django_db
def test_legacy_trade_r_derived_from_initial_stop(user):
    _trade(user, 10, r=None)   # entry 100, initial stop 95, qty 1 -> risk 5 -> 2R
    start, end = _window()
    assert build_diagnostics(user, start, end)["calibration"]["by_grade"][0]["avg_r"] == 2.0


@pytest.mark.django_db
def test_exit_quality(user):
    _trade(user, -5, r=-1.0, mfe_r=0.8, mae_r=1.0, reason="Stop loss hit")     # stopped after favorable
    _trade(user, -5, r=-1.0, mfe_r=0.1, mae_r=1.0, reason="Stop loss hit")     # stopped, never favorable
    _trade(user, 10, r=2.0, mfe_r=3.0, mae_r=0.4, reason="take profit")        # winner: gave back 1R
    _trade(user, 3, r=None, mfe_r=None, mae_r=None)                            # no excursion data
    start, end = _window()
    eq = build_diagnostics(user, start, end)["exit_quality"]

    assert eq["trades_with_excursion"] == 3
    assert eq["stopped_trades"] == 2 and eq["stopped_after_favorable_pct"] == 50.0
    assert eq["avg_giveback_r"] == round((1.8 + 1.1 + 1.0) / 3, 4)
    assert eq["winners_avg_mae_r"] == 0.4 and eq["losers_avg_mfe_r"] == 0.45


@pytest.mark.django_db
def test_mode_and_date_filters(user):
    _trade(user, 1, r=0.1, is_paper=True)
    _trade(user, 1, r=0.1, is_paper=False)
    _trade(user, 1, r=0.1, closed_at=timezone.now() - timedelta(days=60))
    start, end = _window()
    assert build_diagnostics(user, start, end, "all")["data_notes"]["trades_total"] == 2
    assert build_diagnostics(user, start, end, "paper")["data_notes"]["trades_total"] == 1
    assert build_diagnostics(user, start, end, "live")["data_notes"]["trades_total"] == 1


@pytest.mark.django_db
def test_other_users_data_never_included(user):
    other = get_user_model().objects.create_user("o@example.com", password="pw")
    _trade(other, 9, r=1.0)
    _decision(other, "funding", "sl")
    start, end = _window()
    out = build_diagnostics(user, start, end)
    assert out["data_notes"] == {**out["data_notes"], "trades_total": 0, "decisions_total": 0}
    assert out["gates"] == []


@pytest.mark.django_db
def test_empty_state_shape(user):
    start, end = _window()
    out = build_diagnostics(user, start, end)
    assert out["gates"] == [] and out["calibration"]["by_grade"] == []
    assert out["exit_quality"]["avg_giveback_r"] is None
    assert out["min_sample"] == 30
    assert isinstance(start, date)
