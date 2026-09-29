from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import SignalDecision
from apps.trading.services.outcome_service import evaluate_window, resolve_outcomes


def c(ts, high, low):
    return {"timestamp": ts, "high": high, "low": low}


def test_long_tp1_first():
    out = evaluate_window("LONG", 100, 97, 103, [c(1, 101, 99), c(2, 104, 100), c(3, 105, 96)])
    assert out["first_hit"] == "tp1"        # TP touched in candle 2, before the later SL touch
    assert out["max_fav_pct"] == 5.0 and out["max_adv_pct"] == 4.0   # whole-window extremes


def test_long_sl_first():
    assert evaluate_window("LONG", 100, 97, 103, [c(1, 101, 96), c(2, 104, 100)])["first_hit"] == "sl"


def test_both_levels_in_one_candle_is_ambiguous():
    assert evaluate_window("LONG", 100, 97, 103, [c(1, 104, 96)])["first_hit"] == "ambiguous"


def test_neither_level_touched():
    out = evaluate_window("LONG", 100, 97, 103, [c(1, 101, 99)])
    assert out["first_hit"] == "none" and out["max_fav_pct"] == 1.0 and out["max_adv_pct"] == 1.0


def test_short_side_mirrors():
    assert evaluate_window("SHORT", 100, 103, 97, [c(1, 101, 96)])["first_hit"] == "tp1"
    assert evaluate_window("SHORT", 100, 103, 97, [c(1, 104, 99)])["first_hit"] == "sl"


def test_missing_levels_reported():
    assert evaluate_window("LONG", 100, None, None, [c(1, 101, 99)])["first_hit"] == "no_levels"


class FakeClient:
    def __init__(self, candles):
        self.candles = candles
        self.calls = []

    def fetch_klines_range(self, symbol, interval, start_ms, end_ms):
        self.calls.append((symbol, interval))
        return self.candles


@pytest.fixture
def decision(db):
    user = get_user_model().objects.create_user("a@example.com", password="pw", is_staff=True)
    return SignalDecision.objects.create(
        user=user, symbol="BTCUSDT", side="LONG", result="funding", price=100,
        ref_stop=97, ref_tp1=103, levels_source="default", signal_candle_ts=1,
    )


def _ms(dt):
    return int(dt.timestamp() * 1000)


@pytest.mark.django_db
def test_due_window_resolved_and_others_left_untouched(decision):
    now = decision.created_at + timedelta(hours=1, minutes=5)
    candles = [c(_ms(decision.created_at) + 60_000, 104, 99)]
    counts = resolve_outcomes(now=now, client=FakeClient(candles))
    decision.refresh_from_db()
    assert decision.outcome_1h["status"] == "resolved" and decision.outcome_1h["first_hit"] == "tp1"
    assert decision.outcome_4h == {} and decision.outcome_24h == {}   # not due yet
    assert counts["resolved"] == 1


@pytest.mark.django_db
def test_fetch_failure_leaves_pending_then_unavailable(decision):
    resolve_outcomes(now=decision.created_at + timedelta(hours=2), client=FakeClient(None))
    decision.refresh_from_db()
    assert decision.outcome_1h == {"status": "pending"}    # never fabricated

    resolve_outcomes(now=decision.created_at + timedelta(hours=1 + 49), client=FakeClient(None))
    decision.refresh_from_db()
    assert decision.outcome_1h == {"status": "unavailable"}


@pytest.mark.django_db
def test_resolved_window_is_never_overwritten(decision):
    now = decision.created_at + timedelta(hours=1, minutes=5)
    ts = _ms(decision.created_at) + 60_000
    resolve_outcomes(now=now, client=FakeClient([c(ts, 104, 99)]))
    first = SignalDecision.objects.get(pk=decision.pk).outcome_1h
    resolve_outcomes(now=now + timedelta(minutes=5), client=FakeClient([c(ts, 90, 80)]))
    assert SignalDecision.objects.get(pk=decision.pk).outcome_1h == first


@pytest.mark.django_db
def test_fetches_are_grouped_per_symbol_and_interval(decision):
    SignalDecision.objects.create(
        user=decision.user, symbol="BTCUSDT", side="SHORT", result="atr_spike", price=100,
        signal_candle_ts=2,
    )
    client = FakeClient([])
    resolve_outcomes(now=decision.created_at + timedelta(hours=5), client=client)
    # 1h and 4h share the 1m stream and 24h is not due yet -> a single request
    assert client.calls == [("BTCUSDT", "1m")]
