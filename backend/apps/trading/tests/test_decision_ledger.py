from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading.models import SignalDecision, Trade, TradingBotConfig
from apps.trading.services.decision_ledger_service import (
    GateCode,
    prune_old_decisions,
    record_rejection,
    record_taken,
)
from apps.trading.services.signal_service import SignalResult


def _evaluation(signal: SignalResult, candle_ts=1_700_000_000_000, price=100.0, atr=2.0):
    return SimpleNamespace(
        snapshot=SimpleNamespace(
            payload={"confidence_score": 70, "trade_grade": "B", "regime": "TRENDING", "setup_tags": ["pullback"]}
        ),
        indicators=SimpleNamespace(atr=atr, candles=[{"timestamp": candle_ts}]),
        metrics={"price": price},
        signal=signal,
    )


def _signal(kind="LONG", long_score=60, short_score=0, gate=None):
    return SignalResult(kind, long_score, short_score, ["r"], "CONFIRMED_UPTREND", 1.0, blocked_gate=gate)


@pytest.fixture
def config(db):
    user = get_user_model().objects.create_user("admin@example.com", password="pw", is_staff=True)
    return TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", entry_score_threshold=55)


@pytest.mark.django_db
def test_post_score_rejection_is_stored_with_gate_and_context(config):
    row = record_rejection(config, _evaluation(_signal()), GateCode.FUNDING)

    assert row.result == "funding"
    assert (row.symbol, row.side, row.score, row.grade, row.regime) == ("BTCUSDT", "LONG", 60, "B", "TRENDING")
    assert float(row.price) == 100.0
    # no risk plan yet -> default 1.5 ATR levels, marked as such
    assert row.levels_source == "default"
    assert float(row.ref_stop) == 97.0 and float(row.ref_tp1) == 103.0
    assert row.is_paper is True


@pytest.mark.django_db
def test_short_default_levels_are_mirrored(config):
    row = record_rejection(config, _evaluation(_signal("SHORT", 0, 60)), GateCode.FUNDING)
    assert float(row.ref_stop) == 103.0 and float(row.ref_tp1) == 97.0


@pytest.mark.django_db
def test_same_gate_same_candle_is_stored_once(config):
    ev = _evaluation(_signal())
    record_rejection(config, ev, GateCode.FUNDING)
    record_rejection(config, ev, GateCode.FUNDING)
    assert SignalDecision.objects.count() == 1
    # a new candle or a different gate is a new fact
    record_rejection(config, _evaluation(_signal(), candle_ts=1_700_000_900_000), GateCode.FUNDING)
    record_rejection(config, ev, GateCode.MA7_SLOPE)
    assert SignalDecision.objects.count() == 3


@pytest.mark.django_db
def test_score_level_gate_needs_a_near_candidate(config):
    far = _evaluation(_signal("NO_TRADE", 20, 0, gate="pullback_zone"))
    near = _evaluation(_signal("NO_TRADE", 40, 0, gate="pullback_zone"))  # 40 >= 0.6 * 55
    assert record_rejection(config, far, "pullback_zone") is None
    assert record_rejection(config, near, "pullback_zone").side == "LONG"


@pytest.mark.django_db
def test_no_directional_score_is_not_a_candidate(config):
    assert record_rejection(config, _evaluation(_signal("NO_TRADE", 0, 0, gate="ma_alignment")), "ma_alignment") is None


@pytest.mark.django_db
def test_short_uses_short_threshold_for_floor(config):
    config.short_entry_score_threshold = 80
    config.save()
    ev = _evaluation(_signal("NO_TRADE", 0, 40, gate="pullback_zone"))  # 40 < 0.6 * 80
    assert record_rejection(config, ev, "pullback_zone") is None


@pytest.mark.django_db
def test_followers_do_not_write_decisions(config):
    follower = get_user_model().objects.create_user("f@example.com", password="pw")
    fconfig = TradingBotConfig.objects.create(user=follower, symbol="ETHUSDT")
    assert record_rejection(fconfig, _evaluation(_signal()), GateCode.FUNDING) is None
    assert SignalDecision.objects.count() == 0


@pytest.mark.django_db
def test_taken_decision_links_trade_and_uses_planner_levels(config):
    trade = Trade.objects.create(
        user=config.user, symbol="BTCUSDT", side="LONG", entry_price=100, quantity=1,
        stop_loss=95, take_profit_1=105, take_profit_2=110, take_profit_3=115, open_reason="x",
    )
    plan = SimpleNamespace(stop_loss=95, take_profit_1=105)
    row = record_taken(config, _evaluation(_signal()), trade, plan)
    assert row.result == "taken" and row.trade_id == trade.pk
    assert row.levels_source == "planner" and float(row.ref_stop) == 95.0


@pytest.mark.django_db
def test_recording_failure_never_raises(config):
    broken = SimpleNamespace(signal=_signal(), snapshot=None, indicators=None, metrics={})
    assert record_rejection(config, broken, GateCode.FUNDING) is None
    assert record_taken(config, broken, None) is None


@pytest.mark.django_db
def test_prune_removes_only_rows_past_retention(config):
    old = record_rejection(config, _evaluation(_signal()), GateCode.FUNDING)
    fresh = record_rejection(config, _evaluation(_signal(), candle_ts=1), GateCode.FUNDING)
    SignalDecision.objects.filter(pk=old.pk).update(created_at=timezone.now() - timezone.timedelta(days=91))
    assert prune_old_decisions() == 1
    assert list(SignalDecision.objects.values_list("pk", flat=True)) == [fresh.pk]


def test_gate_codes_are_unique_strings():
    assert len(GateCode.ALL) == len(set(GateCode.ALL)) > 20
