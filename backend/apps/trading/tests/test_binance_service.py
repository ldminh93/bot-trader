import json
import threading
import time
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest
from django.test import override_settings

from apps.trading.services import binance_service as binance_service_module
from apps.trading.services.binance_service import BinanceAPIError, BinanceService, SymbolRules


def response(status_code: int, payload: dict) -> Mock:
    result = Mock()
    result.status_code = status_code
    result.is_error = status_code >= 400
    result.reason_phrase = "Unauthorized"
    result.json.return_value = payload
    return result


@override_settings(BINANCE_TESTNET=False)
@patch("apps.trading.services.binance_service.httpx.request")
def test_connection_reports_missing_futures_trade_permission(request):
    request.side_effect = [
        response(200, {"canTrade": True}),
        response(200, {"enableFutures": False, "ipRestrict": True}),
    ]

    result = BinanceService("key", "secret").test_connection()

    assert result["connected"] is True
    assert result["can_trade"] is False
    assert result["futures_enabled"] is False
    assert "Enable Futures trading is disabled" in result["message"]


@patch("apps.trading.services.binance_service.httpx.request")
def test_signed_error_omits_signature_url(request):
    request.return_value = response(
        401,
        {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action"},
    )

    with pytest.raises(BinanceAPIError) as exc_info:
        BinanceService("key", "secret").set_margin_type("BTCUSDT", "isolated")

    assert exc_info.value.code == -2015
    assert "signature=" not in str(exc_info.value)
    assert "Invalid API-key" in str(exc_info.value)


@patch("apps.trading.services.binance_service.httpx.request")
def test_user_trades_chunks_windows_longer_than_seven_days(request):
    """
    /fapi/v1/userTrades rejects a startTime more than 7 days before endTime
    (error -1127). A position held open longer than a week must still get
    its full fill history instead of that single call failing outright —
    this is the bug behind closed-trade PnL not matching Binance's actual
    numbers for any trade that wasn't closed within a week of opening.
    """
    now_ms = 1_700_000_000_000
    start_ms = now_ms - (15 * 24 * 60 * 60 * 1000)  # opened 15 days ago
    request.side_effect = [
        response(200, [{"id": 1, "side": "BUY", "price": "100", "qty": "1", "realizedPnl": "0", "commission": "0.01"}]),
        response(200, [{"id": 2, "side": "SELL", "price": "110", "qty": "1", "realizedPnl": "10", "commission": "0.01"}]),
        response(200, []),
    ]

    with patch("apps.trading.services.binance_service.time.time", return_value=now_ms / 1000):
        fills = BinanceService("key", "secret").user_trades("BTCUSDT", start_ms)

    assert [f["id"] for f in fills] == [1, 2]
    assert request.call_count == 3
    called_windows = [call.args[1].split("?", 1)[1] for call in request.call_args_list]
    for window in called_windows:
        assert "startTime=" in window and "endTime=" in window


@patch("apps.trading.services.binance_service.httpx.request")
def test_place_close_algo_order_rejects_trailing_stop_with_close_position(request):
    """
    Reproduces the reported bug: Binance rejects TRAILING_STOP_MARKET combined
    with closePosition=true outright (error -4136 "Target strategy invalid for
    orderType TRAILING_STOP_MARKET,closePosition true") — unlike STOP_MARKET/
    TAKE_PROFIT_MARKET, it only ever accepts an explicit quantity. Catch this
    locally instead of round-tripping to Binance to find out.
    """
    with pytest.raises(ValueError, match="close_position"):
        BinanceService("key", "secret").place_close_algo_order(
            "BTCUSDT",
            "SELL",
            "TRAILING_STOP_MARKET",
            Decimal("100"),
            "client-id",
            close_position=True,
            callback_rate=Decimal("3.0"),
        )
    request.assert_not_called()


def _rules() -> SymbolRules:
    return SymbolRules(
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_notional=Decimal("5"),
    )


def test_normalize_order_rejects_below_min_notional_by_default():
    with pytest.raises(ValueError, match="minimum notional"):
        BinanceService.normalize_order(Decimal("100"), Decimal("0.001"), _rules())


def test_normalize_order_skips_min_notional_check_when_requested():
    """
    Closing an existing position (e.g. the runner leftover after TP1/TP2 fills)
    must not be blocked by the same MIN_NOTIONAL floor that guards new entries —
    otherwise the position gets permanently stuck retrying an unwinnable close.
    """
    price, quantity = BinanceService.normalize_order(
        Decimal("100"), Decimal("0.001"), _rules(), skip_min_notional=True
    )
    assert price == Decimal("100.00")
    assert quantity == Decimal("0.001")


class _FakeLock:
    """Stands in for redis-py's Lock, backed by a real threading.Lock so
    tests exercise actual blocking/contention instead of just call counts."""

    def __init__(self, lock: threading.Lock, blocking_timeout: float | None):
        self._lock = lock
        self._blocking_timeout = blocking_timeout

    def acquire(self) -> bool:
        timeout = self._blocking_timeout if self._blocking_timeout is not None else -1
        return self._lock.acquire(timeout=timeout)

    def release(self) -> None:
        self._lock.release()


class _FakeRedis:
    """Minimal in-memory stand-in for the get/set/lock surface
    _with_singleflight_cache relies on."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}
        self._data_lock = threading.Lock()
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    def get(self, key: str):
        with self._data_lock:
            return self._data.get(key)

    def set(self, key: str, value: str, ex=None) -> None:
        with self._data_lock:
            self._data[key] = value

    def lock(self, name: str, timeout=None, blocking_timeout=None) -> _FakeLock:
        with self._locks_lock:
            lock = self._locks.setdefault(name, threading.Lock())
        return _FakeLock(lock, blocking_timeout)


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(binance_service_module, "_redis_client", fake)
    return fake


def test_singleflight_cache_hit_skips_fetch_fn(fake_redis):
    fake_redis.set("k", json.dumps({"v": 1}))
    calls = []

    result = binance_service_module._with_singleflight_cache(
        "k", 20, lambda: calls.append(1) or {"v": 2}
    )

    assert result == {"v": 1}
    assert calls == []


def test_singleflight_cache_miss_calls_fetch_fn_and_caches_result(fake_redis):
    result = binance_service_module._with_singleflight_cache("k", 20, lambda: {"v": 42})

    assert result == {"v": 42}
    assert json.loads(fake_redis.get("k")) == {"v": 42}


def test_singleflight_cache_does_not_cache_a_none_result(fake_redis):
    """A None from fetch_fn signals an upstream error (see fetch_klines/
    market_metrics/_fetch_24hr_tickers callers) — it must fall through to the
    caller's own mock-data fallback, not get poisoned into the cache and
    served as if it were real data for the rest of the TTL."""
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return None

    first = binance_service_module._with_singleflight_cache("k", 20, fetch)
    second = binance_service_module._with_singleflight_cache("k", 20, fetch)

    assert first is None
    assert second is None
    assert fake_redis.get("k") is None
    assert calls["n"] == 2


def test_singleflight_cache_dedupes_concurrent_misses(fake_redis):
    """
    Reproduces the bug the mirror-trade feature exposed: once every regular
    user's scanner list is force-mirrored from admin's
    (coin_mirror_service.mirror_admin_coins_to_regular_users), N users can end
    up with N TradingBotConfig rows for the same symbol/timeframe, and
    run_active_bots dispatches them concurrently. Before this fix, all N
    threads could miss the cache for that symbol's data at the same instant
    and all hit Binance in parallel for identical data — the request-weight
    multiplication that tripped the per-IP -1003 ban and stopped every user's
    bots from opening positions. Only the first concurrent caller for a given
    key should run fetch_fn; the rest must wait and reuse its result.
    """
    call_count = {"n": 0}
    call_count_lock = threading.Lock()

    def fetch():
        with call_count_lock:
            call_count["n"] += 1
        time.sleep(0.2)
        return {"v": "shared"}

    results = []
    results_lock = threading.Lock()

    def worker():
        result = binance_service_module._with_singleflight_cache("k", 20, fetch)
        with results_lock:
            results.append(result)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert call_count["n"] == 1
    assert results == [{"v": "shared"}] * 10


@patch("apps.trading.services.binance_service.httpx.get")
def test_fetch_klines_dedupes_concurrent_requests_for_same_symbol(get, fake_redis):
    """End-to-end version of the dedup fix through the actual public method
    that mirroring's stampede hit: concurrent bot cycles fetching klines for
    the same symbol/interval must only make one real Binance request."""
    row = [1700000000000, "1", "2", "0.5", "1.5", "10", 1700000060000, "0", "0", "5", "0", "0"]

    def slow_response(*args, **kwargs):
        time.sleep(0.2)
        return response(200, [row])

    get.side_effect = slow_response
    results = []
    results_lock = threading.Lock()

    def worker():
        candles = BinanceService().fetch_klines("BTCUSDT", "15m")
        with results_lock:
            results.append(candles)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert get.call_count == 1
    assert len(results) == 8
    assert all(r == results[0] for r in results)

