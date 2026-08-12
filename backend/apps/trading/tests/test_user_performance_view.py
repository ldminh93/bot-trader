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


def _seed_users():
    User = get_user_model()
    admin = User.objects.create_user("admin@example.com", password="secure-pass", is_staff=True)
    regular = User.objects.create_user("regular@example.com", password="secure-pass")
    with_trades = User.objects.create_user("trader@example.com", password="secure-pass")
    no_trades = User.objects.create_user("newcomer@example.com", password="secure-pass")

    _trade(with_trades, symbol="BTCUSDT", realized_pnl=50)
    _trade(with_trades, symbol="ETHUSDT", realized_pnl=-20)
    _trade(with_trades, symbol="SOLUSDT", status=Trade.Status.OPEN, unrealized_pnl=10)

    return admin, regular, with_trades, no_trades


def _entry_for(results, username):
    return next(entry for entry in results if entry["username"] == username)


@pytest.mark.django_db
def test_staff_can_list_all_users_with_performance():
    admin, regular, with_trades, no_trades = _seed_users()
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get("/api/users/performance")

    assert response.status_code == 200
    results = response.json()["results"]
    assert {entry["username"] for entry in results} == {
        "admin@example.com",
        "regular@example.com",
        "trader@example.com",
        "newcomer@example.com",
    }

    trader_entry = _entry_for(results, "trader@example.com")
    assert trader_entry["total_trades"] == 2
    assert trader_entry["win_rate"] == 50.0
    assert trader_entry["total_profit"] == 40.0
    assert trader_entry["is_active"] is True

    newcomer_entry = _entry_for(results, "newcomer@example.com")
    assert newcomer_entry["total_trades"] == 0
    assert newcomer_entry["win_rate"] is None
    assert newcomer_entry["total_profit"] == 0


@pytest.mark.django_db
def test_deactivated_user_is_marked_inactive():
    admin, regular, with_trades, no_trades = _seed_users()
    no_trades.is_active = False
    no_trades.save(update_fields=["is_active"])
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get("/api/users/performance")

    entry = _entry_for(response.json()["results"], "newcomer@example.com")
    assert entry["is_active"] is False


@pytest.mark.django_db
def test_ordering_by_total_profit_descending_is_default():
    admin, regular, with_trades, no_trades = _seed_users()
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get("/api/users/performance")

    profits = [entry["total_profit"] for entry in response.json()["results"]]
    assert profits == sorted(profits, reverse=True)


@pytest.mark.django_db
def test_ordering_by_win_rate_ascending():
    admin, regular, with_trades, no_trades = _seed_users()
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get("/api/users/performance?ordering=win_rate")

    results = response.json()["results"]
    real_win_rates = [entry["win_rate"] for entry in results if entry["win_rate"] is not None]
    assert real_win_rates == sorted(real_win_rates)
    # Users with no closed trades (win_rate: null) are pushed to the tail,
    # regardless of sort direction.
    assert [entry["win_rate"] for entry in results[-2:]].count(None) >= 1


@pytest.mark.django_db
def test_ordering_ties_break_by_username_ascending():
    User = get_user_model()
    admin = User.objects.create_user("admin@example.com", password="secure-pass", is_staff=True)
    User.objects.create_user("zed@example.com", password="secure-pass")
    User.objects.create_user("amy@example.com", password="secure-pass")
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get("/api/users/performance")

    # All three users have $0 profit (no trades) -> tie broken by username asc.
    usernames = [entry["username"] for entry in response.json()["results"]]
    assert usernames == sorted(usernames)


@pytest.mark.django_db
def test_search_filters_by_username_or_email():
    admin, regular, with_trades, no_trades = _seed_users()
    client = APIClient()
    client.force_authenticate(admin)

    response = client.get("/api/users/performance?search=trader")

    usernames = {entry["username"] for entry in response.json()["results"]}
    assert usernames == {"trader@example.com"}


@pytest.mark.django_db
def test_non_staff_user_is_denied_with_no_user_data():
    admin, regular, with_trades, no_trades = _seed_users()
    client = APIClient()
    client.force_authenticate(regular)

    response = client.get("/api/users/performance")

    assert response.status_code == 403
    assert "results" not in response.json()


@pytest.mark.django_db
def test_anonymous_request_is_denied_with_no_user_data():
    client = APIClient()

    response = client.get("/api/users/performance")

    assert response.status_code in (401, 403)
    assert "results" not in response.json()
