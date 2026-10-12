from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.trading.models import SignalDecision
from apps.trading.services.level_sweep_service import (
    ROUND_TRIP_FEE_PCT,
    build_level_sweep,
    classify,
    decision_atr,
)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("s@example.com", password="pw", is_staff=True)


def _window():
    today = timezone.localdate()
    return today - timedelta(days=7), today


def _decision(user, fav, adv, *, atr=1.0, price=100, result="taken", window="outcome_24h", status="resolved", **kw):
    fields = dict(
        user=user, symbol="BTCUSDT", side="LONG", result=result, price=price, atr=atr,
        levels_source="planner", signal_candle_ts=SignalDecision.objects.count() + 1,
    )
    fields.update(kw)
    d = SignalDecision.objects.create(**fields)
    setattr(d, window, {"status": status, "first_hit": "none", "max_fav_pct": fav, "max_adv_pct": adv})
    d.save()
    return d


def _cell(out, stop, target):
    return next(c for c in out["cells"] if c["stop_atr"] == stop and c["target_r"] == target)


def test_classify():
    assert classify(2.0, 0.5, 1.0, 1.5) == "win"
    assert classify(0.5, 1.0, 1.0, 1.5) == "loss"       # touching the stop counts as stopped
    assert classify(2.0, 1.5, 1.0, 1.5) == "ambiguous"
    assert classify(0.5, 0.5, 1.0, 1.5) == "open"


@pytest.mark.django_db
def test_decision_atr_falls_back_to_default_levels(user):
    stored = _decision(user, 0, 0, atr=2.0)
    implied = _decision(user, 0, 0, atr=None, levels_source="default", ref_stop=97)   # 3 / 1.5
    planner = _decision(user, 0, 0, atr=None, levels_source="planner", ref_stop=97)
    assert decision_atr(stored) == 2.0
    assert decision_atr(implied) == pytest.approx(2.0)
    assert decision_atr(planner) is None


@pytest.mark.django_db
def test_cell_counts_and_fee_adjusted_expectancy(user):
    # ATR = 1% of price. Stop 1 ATR = 1%, target 2R = 2%.
    _decision(user, fav=2.5, adv=0.4)   # win
    _decision(user, fav=0.3, adv=1.2)   # loss
    _decision(user, fav=2.2, adv=1.1)   # ambiguous
    _decision(user, fav=0.5, adv=0.5)   # open
    start, end = _window()
    cell = _cell(build_level_sweep(user, start, end), 1.0, 2.0)
    fee_r = ROUND_TRIP_FEE_PCT / 1.0
    assert cell["samples"] == 4 and cell["decided"] == 2
    assert cell["win_rate"] == 50.0 and cell["ambiguous_pct"] == 25.0 and cell["open_pct"] == 25.0
    assert cell["expectancy_r"] == pytest.approx(round((2.0 - fee_r + -1.0 - fee_r) / 2, 3))
    assert cell["worst_case_r"] == pytest.approx(round((2.0 - fee_r - 2 * (1.0 + fee_r)) / 3, 3))
    assert cell["low_sample"] is True


@pytest.mark.django_db
def test_skips_unresolved_and_counts_missing_atr(user):
    _decision(user, 1, 1, status="pending")
    _decision(user, 1, 1, atr=None)
    _decision(user, 1, 1)
    start, end = _window()
    out = build_level_sweep(user, start, end)
    assert out["samples"] == 1 and out["skipped_no_atr"] == 1
    assert len(out["cells"]) == len(out["stops_atr"]) * len(out["targets_r"])


@pytest.mark.django_db
def test_population_and_best_cell(user):
    # ATR 1%: a 0.75 ATR stop is touched (0.9 >= 0.75) so that row is ambiguous; 1 ATR survives and 2R (2%) is reached
    # (+2R minus fees), which beats every wider-stop / smaller-target pair.
    for _ in range(40):
        _decision(user, fav=2.05, adv=0.9)
    _decision(user, fav=5, adv=5, result="funding")  # excluded from the taken population
    start, end = _window()
    taken = build_level_sweep(user, start, end, population="taken")
    assert taken["samples"] == 40
    assert taken["best"] == {"stop_atr": 1.0, "target_r": 2.0}
    assert _cell(taken, 0.75, 2.0)["ambiguous_pct"] == 100.0
    assert build_level_sweep(user, start, end)["samples"] == 41


@pytest.mark.django_db
def test_endpoint_validates_and_scopes(user):
    other = get_user_model().objects.create_user("o@example.com", password="pw")
    _decision(other, 1, 1)
    client = APIClient()
    client.force_authenticate(user)
    assert client.get("/api/diagnostics/levels?population=bad").status_code == 400
    assert client.get("/api/diagnostics/levels?window=2h").status_code == 400
    body = client.get("/api/diagnostics/levels").json()
    assert body["window"] == "24h" and body["population"] == "all" and body["samples"] == 0
