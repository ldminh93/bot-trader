from dataclasses import replace
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model

from apps.trading.models import MarketSnapshot, Trade, TradingBotConfig
from apps.trading.services.indicator_service import IndicatorResult
from apps.trading.services.market_snapshot_service import MarketEvaluation
from apps.trading.services.signal_service import SignalResult
from apps.trading.tasks import process_config

User = get_user_model()

PRICE, MA7, MA25, MA99, ATR = 100.0, 99.0, 97.0, 95.0, 1.0


def _make_config(user, **overrides) -> TradingBotConfig:
    defaults = dict(
        user=user,
        symbol="BTCUSDT",
        is_running=True,
        # Keeps this test focused on the core entry path — the MA-distance
        # entry-location gate is exercised separately elsewhere.
        pullback_entry_enabled=False,
        live_mode_requested=False,
    )
    defaults.update(overrides)
    return TradingBotConfig.objects.create(**defaults)


def _favorable_evaluation(config: TradingBotConfig, signal: str = "LONG") -> MarketEvaluation:
    """A snapshot/signal pair that clears every default entry filter (all of
    which are 0/disabled or have no prior trade history to trip on for a
    fresh test user) so the resulting Trade reflects only the signal itself."""
    snapshot = MarketSnapshot.objects.create(
        symbol=config.symbol,
        timeframe=config.timeframe_signal,
        price=Decimal(str(PRICE)),
        ma7=Decimal(str(MA7)),
        ma25=Decimal(str(MA25)),
        ma99=Decimal(str(MA99)),
        delta=Decimal("0"),
        cvd=Decimal("0"),
        open_interest=Decimal("1000"),
        open_interest_change_percent=Decimal("1"),
        funding_rate=Decimal("0"),
        top_trader_account_ratio=Decimal("1"),
        top_trader_position_ratio=Decimal("1"),
        adx=Decimal("30"),
        atr=Decimal(str(ATR)),
        volume=Decimal("100"),
        volume_ma20=Decimal("80"),
        trend="CONFIRMED_UPTREND",
        payload={
            "signal": signal,
            "regime": "TRENDING",
            "regime_label": "Trending",
            "confidence_score": 80,
            "trade_grade": "A",
            "opportunity_score": 100,
            "effective_leverage": config.leverage,
            "tp_r_multiple": 3.0,
            "higher_timeframe_bias": {"alignment": "aligned"},
            "setup_tags": [],
            "reasons": ["trend confirmed"],
            "trend_state": "CONFIRMED_UPTREND",
        },
    )
    indicators = IndicatorResult(
        candles=[],
        price=PRICE,
        ma7=MA7,
        ma25=MA25,
        ma99=MA99,
        delta=0.0,
        cvd=0.0,
        atr=ATR,
        atr_ma20=ATR,
        adx=30.0,
        volume=100.0,
        volume_ma20=80.0,
        swing_high=PRICE + 5,
        swing_low=PRICE - 5,
    )
    metrics = {
        "price": PRICE,
        "open_interest": 1000.0,
        "open_interest_change_percent": 1.0,
        "open_interest_change_available": True,
        "funding_rate": 0.0,
        "top_trader_account_ratio": 1.0,
        "top_trader_position_ratio": 1.0,
        "top_ratio_direction": 0.0,
        "statistics_period": "15m",
        "source": "test",
    }
    signal_result = SignalResult(
        signal=signal,
        long_score=80 if signal == "LONG" else 0,
        short_score=80 if signal == "SHORT" else 0,
        reasons=["trend confirmed"],
        trend_state="CONFIRMED_UPTREND" if signal != "SHORT" else "CONFIRMED_DOWNTREND",
        risk_multiplier=1.0,
    )
    return MarketEvaluation(snapshot=snapshot, indicators=indicators, metrics=metrics, signal=signal_result)


@pytest.mark.django_db
@patch("apps.trading.tasks.broadcast_user_update")
@patch("apps.trading.tasks.collect_market_snapshot")
def test_admin_opens_paper_position_on_favorable_signal(mock_snapshot, mock_broadcast):
    """
    Regression test for the mirror-trade stampede bug: when market data is
    available and a real LONG/SHORT signal clears every entry filter, an
    admin's bot cycle must still open a Trade. This is exactly the behavior
    that silently broke when the per-IP Binance ban (see binance_service.py
    _with_singleflight_cache) made every collect_market_snapshot call raise
    before a signal was ever produced — no exception here means the entry
    path itself is intact independent of that fix.
    """
    admin = User.objects.create_user("admin-open@example.com", password="secure-pass", is_staff=True)
    config = _make_config(admin)
    mock_snapshot.return_value = _favorable_evaluation(config)

    process_config(config)

    trade = Trade.objects.get(user=admin, symbol=config.symbol)
    assert trade.side == Trade.Side.LONG
    assert trade.status == Trade.Status.OPEN
    assert trade.is_paper is True


@pytest.mark.django_db
@patch("apps.trading.tasks.broadcast_user_update")
@patch("apps.trading.tasks.collect_market_snapshot")
def test_no_trade_signal_does_not_open_a_position(mock_snapshot, mock_broadcast):
    admin = User.objects.create_user("admin-no-trade@example.com", password="secure-pass", is_staff=True)
    config = _make_config(admin)
    mock_snapshot.return_value = _favorable_evaluation(config, signal="NO_TRADE")

    process_config(config)

    assert not Trade.objects.filter(user=admin, symbol=config.symbol).exists()


@pytest.mark.django_db
@patch("apps.trading.tasks.broadcast_user_update")
@patch("apps.trading.tasks.collect_market_snapshot")
def test_regular_user_never_opens_its_own_position(mock_snapshot, mock_broadcast):
    """Regular (non-admin) users no longer independently decide entries —
    they only ever receive a mirrored trade via sync_master_trade_to_followers
    once the admin opens one (see tasks.py's `if not config.user.is_staff:
    return` gate). A regular user's own bot cycle, even with a favorable
    signal, must not open anything on its own."""
    regular = User.objects.create_user("regular-open@example.com", password="secure-pass", is_staff=False)
    config = _make_config(regular)
    mock_snapshot.return_value = _favorable_evaluation(config)

    process_config(config)

    assert not Trade.objects.filter(user=regular, symbol=config.symbol).exists()


@pytest.mark.django_db
@patch("apps.trading.tasks.broadcast_user_update")
@patch("apps.trading.tasks.collect_market_snapshot")
def test_ma_stack_reversal_skipped_in_high_volatility_regime(mock_snapshot, mock_broadcast):
    """MA-stack reversal is a counter-trend catch-the-knife pattern that
    otherwise skips the trend-confirmation filters (see tasks.py's
    is_ma_stack_reversal exemptions). It must still be blocked when the
    regime is HIGH_VOLATILITY, since catching a reversal inside a volatility
    spike stacks two independent risks (see the SHORT loss this regressed
    against: confidence 4, regime High volatility, stopped out)."""
    admin = User.objects.create_user("admin-ma-stack@example.com", password="secure-pass", is_staff=True)
    config = _make_config(admin)
    evaluation = _favorable_evaluation(config, signal="SHORT")
    evaluation.snapshot.payload["regime"] = "HIGH_VOLATILITY"
    ma_stack_signal = SignalResult(
        signal="SHORT",
        long_score=0,
        short_score=0,
        reasons=["MA stack reversal"],
        trend_state="CONFIRMED_DOWNTREND",
        risk_multiplier=0.5,
        forced_stop_loss_percent=10.0,
    )
    mock_snapshot.return_value = replace(evaluation, signal=ma_stack_signal)

    process_config(config)

    assert not Trade.objects.filter(user=admin, symbol=config.symbol).exists()


@pytest.mark.django_db
@patch("apps.trading.tasks.broadcast_user_update")
@patch("apps.trading.tasks.collect_market_snapshot")
def test_ma_stack_reversal_still_opens_outside_high_volatility_regime(mock_snapshot, mock_broadcast):
    """Sanity check that the HIGH_VOLATILITY block above is regime-specific
    and doesn't disable the MA-stack reversal pattern entirely."""
    admin = User.objects.create_user("admin-ma-stack-ok@example.com", password="secure-pass", is_staff=True)
    config = _make_config(admin)
    evaluation = _favorable_evaluation(config, signal="SHORT")
    ma_stack_signal = SignalResult(
        signal="SHORT",
        long_score=0,
        short_score=0,
        reasons=["MA stack reversal"],
        trend_state="CONFIRMED_DOWNTREND",
        risk_multiplier=0.5,
        forced_stop_loss_percent=10.0,
    )
    mock_snapshot.return_value = replace(evaluation, signal=ma_stack_signal)

    process_config(config)

    trade = Trade.objects.get(user=admin, symbol=config.symbol)
    assert trade.side == Trade.Side.SHORT


@pytest.mark.django_db
@patch("apps.trading.services.position_sync_service.broadcast_user_update")
@patch("apps.trading.tasks.broadcast_user_update")
@patch("apps.trading.tasks.collect_market_snapshot")
def test_admin_entry_mirrors_to_a_running_follower(mock_snapshot, mock_broadcast, mock_follower_broadcast):
    """End-to-end proof that admin's entry still mirrors to a regular
    follower's account on the same symbol — the exact flow the mirror-trade
    feature added, and what the reported "system doesn't open positions
    anymore" bug actually broke (via the Binance ban stampede, not this
    mirroring logic itself)."""
    admin = User.objects.create_user("admin-mirror@example.com", password="secure-pass", is_staff=True)
    config = _make_config(admin)
    follower = User.objects.create_user("follower-mirror@example.com", password="secure-pass", is_staff=False)
    _make_config(follower)
    mock_snapshot.return_value = _favorable_evaluation(config)

    process_config(config)

    assert Trade.objects.filter(
        user=admin, symbol=config.symbol, status=Trade.Status.OPEN
    ).exists()
    assert Trade.objects.filter(
        user=follower, symbol=config.symbol, status=Trade.Status.OPEN
    ).exists()
