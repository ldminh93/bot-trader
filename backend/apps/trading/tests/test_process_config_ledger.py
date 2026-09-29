"""process_config -> decision ledger wiring, and proof the ledger never affects trading."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import BotLog, MarketSnapshot, SignalDecision, Trade, TradingBotConfig
from apps.trading.services.signal_service import SignalResult
from apps.trading.tasks import process_config


def _evaluation(config, signal):
    snapshot = MarketSnapshot.objects.create(
        symbol=config.symbol, timeframe="15m", price=100,
        payload={"confidence_score": 70, "trade_grade": "B", "regime": "TRENDING", "setup_tags": ["pullback"]},
    )
    indicators = SimpleNamespace(
        atr=2.0, atr_ma20=2.0, candles=[{"timestamp": 1_700_000_000_000}],
        ma7=99.0, ma25=98.0, ma99=90.0, adx=30.0, volume=1.0, volume_ma20=1.0,
    )
    return SimpleNamespace(
        snapshot=snapshot, indicators=indicators, metrics={
            "price": 100.0, "funding_rate": 0.0, "open_interest": 1000.0,
            "open_interest_change_percent": 1.0,
        },
        signal=signal,
    )


@pytest.fixture
def config(db):
    user = get_user_model().objects.create_user("admin@example.com", password="pw", is_staff=True)
    return TradingBotConfig.objects.create(user=user, symbol="BTCUSDT", entry_score_threshold=55)


def _run(config, signal):
    with patch("apps.trading.tasks.collect_market_snapshot", return_value=_evaluation(config, signal)), patch(
        "apps.trading.tasks.broadcast_user_update"
    ):
        process_config(config)


@pytest.mark.django_db
def test_score_level_rejection_is_recorded_with_its_gate(config):
    signal = SignalResult("NO_TRADE", 40, 0, ["blocked"], "CONFIRMED_UPTREND", 1.0, blocked_gate="pullback_zone")

    _run(config, signal)

    row = SignalDecision.objects.get()
    assert (row.result, row.side, row.score, row.symbol) == ("pullback_zone", "LONG", 40, "BTCUSDT")
    assert Trade.objects.count() == 0


@pytest.mark.django_db
def test_cycle_level_rejection_is_recorded_and_still_logged(config):
    config.max_open_positions = 0
    config.save()
    signal = SignalResult("LONG", 60, 0, ["ok"], "CONFIRMED_UPTREND", 1.0)

    _run(config, signal)

    assert SignalDecision.objects.get().result == "max_positions"
    assert BotLog.objects.filter(message__startswith="Maximum open positions reached").exists()
    assert Trade.objects.count() == 0


@pytest.mark.django_db
def test_ledger_failure_does_not_change_cycle_outcome(config):
    config.max_open_positions = 0
    config.save()
    signal = SignalResult("LONG", 60, 0, ["ok"], "CONFIRMED_UPTREND", 1.0)

    with patch("apps.trading.services.decision_ledger_service._store", side_effect=RuntimeError("db down")):
        _run(config, signal)   # must not raise

    assert SignalDecision.objects.count() == 0
    assert BotLog.objects.filter(message__startswith="Maximum open positions reached").exists()
    assert Trade.objects.count() == 0


@pytest.mark.django_db
def test_excursion_failure_does_not_break_open_trade_cycle(config):
    trade = Trade.objects.create(
        user=config.user, symbol="BTCUSDT", side="LONG", entry_price=100, quantity=1,
        stop_loss=95, initial_stop_loss=95, take_profit_1=105, take_profit_2=110, take_profit_3=115,
        open_reason="x",
    )
    signal = SignalResult("LONG", 60, 0, ["ok"], "CONFIRMED_UPTREND", 1.0)

    with patch("apps.trading.tasks.PaperTradingService.update_trade"), patch(
        "apps.trading.tasks.evaluate_early_exit", return_value=SimpleNamespace(should_close=False)
    ), patch("apps.trading.services.excursion_service.compute_excursion", side_effect=RuntimeError("boom")):
        _run(config, signal)   # must not raise

    trade.refresh_from_db()
    assert trade.status == Trade.Status.OPEN


def _entry_state(config):
    trade = Trade.objects.get()
    return (
        trade.side, float(trade.entry_price), float(trade.quantity), float(trade.stop_loss),
        float(trade.take_profit_1), float(trade.take_profit_3), trade.leverage, trade.is_paper,
    )


@pytest.mark.django_db
def test_paper_entry_is_identical_with_or_without_the_ledger(config):
    """Paper-mode regression (SC-006): recording the decision must not alter the trade."""
    # Tag suppression uses a JSON contains lookup that SQLite lacks (Postgres-only, pre-existing).
    config.auto_suppress_losing_tags = False
    config.save()
    signal = SignalResult("LONG", 70, 0, ["ok"], "CONFIRMED_UPTREND", 1.0)

    _run(config, signal)
    with_ledger = _entry_state(config)
    decision = SignalDecision.objects.get()
    assert decision.result == "taken" and decision.trade_id == Trade.objects.get().pk
    assert decision.levels_source == "planner"

    Trade.objects.all().delete()
    SignalDecision.objects.all().delete()
    with patch("apps.trading.services.decision_ledger_service._store", side_effect=RuntimeError("db down")):
        _run(config, signal)

    assert _entry_state(config) == with_ledger
    assert SignalDecision.objects.count() == 0
