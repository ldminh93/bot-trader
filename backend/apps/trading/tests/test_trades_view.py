from datetime import datetime, timezone as dt_timezone

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.models import Trade


def _trade(user, **overrides) -> Trade:
    defaults = dict(
        user=user,
        symbol="BTCUSDT",
        side=Trade.Side.LONG,
        status=Trade.Status.CLOSED,
        entry_price=100,
        quantity=1,
        stop_loss=90,
        take_profit_1=105,
        take_profit_2=110,
        take_profit_3=115,
        open_reason="test",
    )
    defaults.update(overrides)
    return Trade.objects.create(**defaults)


@pytest.mark.django_db
def test_trades_range_filters_closed_trades_by_close_date():
    """
    Reproduces the reported bug: the Calendar page needs every trade relevant
    to the month it's showing, not just the 200 most recent overall — an
    account with more history than that silently lost older months entirely
    under the old flat [:200] cap with no date filter.
    """
    user = get_user_model().objects.create_user("calendar-range@example.com", password="secure-pass")
    in_range = _trade(user, symbol="BTCUSDT")
    Trade.objects.filter(pk=in_range.pk).update(
        closed_at=datetime(2026, 3, 15, tzinfo=dt_timezone.utc)
    )
    out_of_range = _trade(user, symbol="ETHUSDT")
    Trade.objects.filter(pk=out_of_range.pk).update(
        closed_at=datetime(2026, 4, 2, tzinfo=dt_timezone.utc)
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/trades?from=2026-03-01&to=2026-03-31")

    assert response.status_code == 200
    symbols = {row["symbol"] for row in response.data}
    assert symbols == {"BTCUSDT"}


@pytest.mark.django_db
def test_trades_range_includes_open_trades_by_open_date_not_close_date():
    """An OPEN trade has no closed_at yet — it must still show up in the
    calendar month it was *opened* in, not be silently excluded."""
    user = get_user_model().objects.create_user("calendar-open@example.com", password="secure-pass")
    open_trade = _trade(user, symbol="SOLUSDT", status=Trade.Status.OPEN, closed_at=None)
    Trade.objects.filter(pk=open_trade.pk).update(
        opened_at=datetime(2026, 3, 20, tzinfo=dt_timezone.utc)
    )
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/trades?from=2026-03-01&to=2026-03-31")

    assert response.status_code == 200
    assert [row["symbol"] for row in response.data] == ["SOLUSDT"]


@pytest.mark.django_db
def test_trades_range_returns_more_than_200_when_scoped_to_a_month():
    """The 200-row cap only applies to the unscoped 'recent trades' request —
    a range-scoped request must return every matching trade in that period."""
    user = get_user_model().objects.create_user("calendar-many@example.com", password="secure-pass")
    for i in range(205):
        trade = _trade(user, symbol=f"SYM{i}USDT")
        Trade.objects.filter(pk=trade.pk).update(
            closed_at=datetime(2026, 3, 1, tzinfo=dt_timezone.utc)
        )
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/trades?from=2026-03-01&to=2026-03-31")

    assert len(response.data) == 205


@pytest.mark.django_db
def test_trades_without_range_keeps_existing_200_cap_behavior():
    """No from/to params must behave exactly as before — recent-trades callers
    (e.g. the dashboard trade table) are unaffected by this change."""
    user = get_user_model().objects.create_user("dashboard-unaffected@example.com", password="secure-pass")
    _trade(user, symbol="BTCUSDT")
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/trades")

    assert response.status_code == 200
    assert len(response.data) == 1
