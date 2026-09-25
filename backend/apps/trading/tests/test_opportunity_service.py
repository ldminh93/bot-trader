from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.trading.services.opportunity_service import grade_from_context, opportunity_score


def test_grade_from_context_downgrades_counter_trend_setup():
    """Alignment must actually move the grade — it used to be an accepted
    but unused parameter, so an aligned and a counter-trend setup with
    identical confidence/regime graded identically."""
    aligned = grade_from_context(80, "aligned", "LONG", "TRENDING", entry_score_threshold=55)
    counter = grade_from_context(80, "counter", "LONG", "TRENDING", entry_score_threshold=55)

    assert aligned == "B"
    assert counter == "C"


def test_grade_from_context_no_trade_ignores_alignment_and_regime():
    assert grade_from_context(90, "aligned", "NO_TRADE", "EXPANSION") == "D"


def test_opportunity_score_no_trade_ignores_alignment_and_regime_bonuses():
    """A blocked NO_TRADE setup must not accrue the same aligned/regime
    bonuses a real signal gets — those are what let a non-actionable row
    outrank a genuine LONG/SHORT signal in the scoreboard's sort."""
    payload = {
        "signal": "NO_TRADE",
        "confidence_score": 92,
        "higher_timeframe_bias": {"alignment": "aligned"},
        "regime": "EXPANSION",
    }

    assert opportunity_score(payload) == 92


def test_opportunity_score_real_signal_outranks_equally_confident_blocked_setup():
    """Reproduces the bug: at equal confidence, a blocked NO_TRADE setup
    used to stack an unconditional aligned (+15) and regime (+15) bonus on
    top of its raw confidence (70+15+15=100), while a real but counter-trend
    signal only got its regime bonus (70+20+5=95) — so the untradeable
    Grade D row (100) outranked the actionable one (95) in a list labeled
    "Ranked by setup quality". Gating the bonuses on signal != NO_TRADE
    flips this: the blocked row scores its bare confidence (70), and the
    real signal's own +20/+5 now correctly puts it ahead (95 > 70)."""
    blocked_no_trade = {
        "signal": "NO_TRADE",
        "confidence_score": 70,
        "higher_timeframe_bias": {"alignment": "aligned"},
        "regime": "EXPANSION",
    }
    real_signal = {
        "signal": "LONG",
        "confidence_score": 70,
        "higher_timeframe_bias": {"alignment": "counter"},
        "regime": "PULLBACK",
    }

    assert opportunity_score(blocked_no_trade) == 70
    assert opportunity_score(real_signal) == 95
    assert opportunity_score(real_signal) > opportunity_score(blocked_no_trade)


def test_opportunity_score_applies_bonuses_only_to_real_signals():
    aligned_expansion_long = {
        "signal": "LONG",
        "confidence_score": 50,
        "higher_timeframe_bias": {"alignment": "aligned"},
        "regime": "EXPANSION",
    }

    # 50 confidence + 20 signal + 15 aligned + 15 EXPANSION
    assert opportunity_score(aligned_expansion_long) == 100


@pytest.mark.django_db
@patch("apps.trading.views.build_opportunity_scoreboard")
def test_opportunity_scoreboard_view_returns_503_on_unexpected_error(mock_build):
    """
    An unhandled exception used to become a bare 500 with no server-side log,
    which the frontend's fetch handling treated identically to a genuine
    empty board. The view must at least log the failure and return a
    distinguishable error status rather than crashing unlogged.
    """
    mock_build.side_effect = RuntimeError("db hiccup")
    user = get_user_model().objects.create_user("opportunity-error@example.com", password="secure-pass")
    client = APIClient()
    client.force_authenticate(user)

    response = client.get("/api/market/opportunities")

    assert response.status_code == 503
