import time
from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.trading.models import SignalDecision, Trade


@pytest.fixture
def client(db):
    user = get_user_model().objects.create_user("v@example.com", password="pw")
    api = APIClient()
    api.force_authenticate(user)
    api.user = user
    return api


@pytest.mark.django_db
def test_requires_authentication():
    assert APIClient().get("/api/diagnostics").status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query",
    ["start=nope", "end=2026-13-01", "mode=demo", "window=2h", "start=2026-09-10&end=2026-09-01"],
)
def test_bad_parameters_return_400(client, query):
    response = client.get(f"/api/diagnostics?{query}")
    assert response.status_code == 400 and "detail" in response.json()


@pytest.mark.django_db
def test_response_shape_matches_contract(client):
    body = client.get("/api/diagnostics").json()
    assert set(body) == {
        "range", "mode", "window", "min_sample", "gates", "calibration", "expectancy",
        "exit_quality", "data_notes",
    }
    assert set(body["calibration"]) == {"by_score_bucket", "by_grade"}
    assert set(body["expectancy"]) == {"by_tag", "by_regime_side"}
    assert body["mode"] == "all" and body["window"] == "4h"


@pytest.mark.django_db
def test_user_only_sees_own_data(client):
    other = get_user_model().objects.create_user("other@example.com", password="pw")
    SignalDecision.objects.create(
        user=other, symbol="BTCUSDT", side="LONG", result="funding", price=100, signal_candle_ts=1,
    )
    Trade.objects.create(
        user=other, symbol="BTCUSDT", side="LONG", status="CLOSED", entry_price=100, quantity=1,
        stop_loss=95, take_profit_1=105, take_profit_2=110, take_profit_3=115, open_reason="x",
        closed_at=timezone.now(), realized_pnl=Decimal("5"),
    )
    body = client.get("/api/diagnostics").json()
    assert body["data_notes"]["decisions_total"] == 0 and body["data_notes"]["trades_total"] == 0
    assert client.get(f"/api/diagnostics?user={other.pk}").json()["data_notes"]["trades_total"] == 0


@pytest.mark.django_db
def test_large_dataset_responds_within_budget(client):
    user = client.user
    now = timezone.now()
    SignalDecision.objects.bulk_create(
        SignalDecision(
            user=user, symbol="BTCUSDT", side="LONG", result=f"gate_{i % 15}", price=100,
            signal_candle_ts=i, outcome_4h={"status": "resolved", "first_hit": "sl" if i % 2 else "tp1"},
            ref_stop=97, ref_tp1=103,
        )
        for i in range(10_000)
    )
    Trade.objects.bulk_create(
        Trade(
            user=user, symbol="BTCUSDT", side="LONG", status="CLOSED", entry_price=100, quantity=1,
            stop_loss=95, initial_stop_loss=95, take_profit_1=105, take_profit_2=110, take_profit_3=115,
            open_reason="x", closed_at=now - timedelta(hours=i % 48), realized_pnl=Decimal(i % 7 - 3),
            setup_tags=["pullback", f"t{i % 9}"], replay_payload={"confidence_score": 50 + i % 40},
        )
        for i in range(1_000)
    )
    started = time.perf_counter()
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    assert time.perf_counter() - started < 3
    assert response.json()["data_notes"]["decisions_total"] == 10_000
