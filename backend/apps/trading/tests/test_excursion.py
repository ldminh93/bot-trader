from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.trading.models import Trade
from apps.trading.services.excursion_service import (
    compute_r_multiple,
    finalize_trade_metrics,
    update_excursion,
)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("t@example.com", password="pw")


def _trade(user, side="LONG", entry=100, initial_sl=95, **kw):
    defaults = dict(
        user=user, symbol="BTCUSDT", side=side, entry_price=entry, quantity=2,
        stop_loss=initial_sl if initial_sl is not None else 95, initial_stop_loss=initial_sl,
        take_profit_1=105, take_profit_2=110, take_profit_3=115, open_reason="x",
    )
    defaults.update(kw)
    return Trade.objects.create(**defaults)


@pytest.mark.django_db
def test_long_tracks_new_extremes_only(user):
    t = _trade(user)
    assert update_excursion(t, 103) is True      # +3 favorable
    assert update_excursion(t, 98) is True       # -2 adverse
    assert update_excursion(t, 101) is False     # neither extreme moves
    t.refresh_from_db()
    assert float(t.mfe_pct) == 3.0 and float(t.mae_pct) == 2.0
    assert float(t.mfe_r) == 0.6 and float(t.mae_r) == 0.4   # risk per unit = 5


@pytest.mark.django_db
def test_short_side_is_sign_flipped(user):
    t = _trade(user, side="SHORT", initial_sl=105)
    update_excursion(t, 96)    # favorable 4
    update_excursion(t, 102)   # adverse 2
    t.refresh_from_db()
    assert float(t.mfe_r) == 0.8 and float(t.mae_r) == 0.4


@pytest.mark.django_db
def test_pct_tracked_but_r_unavailable_without_initial_stop(user):
    t = _trade(user, initial_sl=None)
    update_excursion(t, 104)
    t.refresh_from_db()
    assert float(t.mfe_pct) == 4.0 and t.mfe_r is None
    assert compute_r_multiple(t) is None


@pytest.mark.django_db
def test_r_multiple_uses_initial_risk_amount(user):
    t = _trade(user)  # risk = 5 * qty 2 = 10 USDT
    t.realized_pnl = Decimal("15")
    assert float(compute_r_multiple(t)) == 1.5
    t.realized_pnl = Decimal("-10")
    assert float(compute_r_multiple(t)) == -1.0


@pytest.mark.django_db
def test_closing_a_trade_finalizes_r_and_exit_excursion(user):
    t = _trade(user)
    update_excursion(t, 102)
    t.status = Trade.Status.CLOSED
    t.exit_price = Decimal("104")
    t.realized_pnl = Decimal("8")
    t.closed_at = timezone.now()
    t.save()  # the post_save hook covers every close path
    t.refresh_from_db()
    assert float(t.r_multiple) == 0.8
    assert float(t.mfe_pct) == 4.0    # the exit price extended the excursion
    assert float(t.mae_pct) == 0.0


@pytest.mark.django_db
def test_second_save_with_final_pnl_recomputes_r(user):
    """Live closes save CLOSED first and realized_pnl in a later write."""
    t = _trade(user)
    t.status = Trade.Status.CLOSED
    t.exit_price = Decimal("110")
    t.save()
    t.realized_pnl = Decimal("20")
    t.save(update_fields=["realized_pnl"])
    t.refresh_from_db()
    assert float(t.r_multiple) == 2.0


@pytest.mark.django_db
def test_legacy_trade_without_initial_stop_stays_unavailable(user):
    t = _trade(user, initial_sl=None)
    t.status = Trade.Status.CLOSED
    t.realized_pnl = Decimal("5")
    t.save()
    t.refresh_from_db()
    assert t.r_multiple is None and t.mfe_r is None


@pytest.mark.django_db
def test_failures_never_raise(user):
    t = _trade(user)
    t.entry_price = None
    assert update_excursion(t, 100) is False
    finalize_trade_metrics(t)  # must not raise
