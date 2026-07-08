import hashlib
import hmac
import math
import random
import time
from urllib.parse import urlencode
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN

import httpx
from django.conf import settings


@dataclass(frozen=True)
class SymbolRules:
    tick_size: Decimal
    step_size: Decimal
    min_notional: Decimal


class BinanceAPIError(RuntimeError):
    def __init__(self, status_code: int, code: int | None, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        code_label = f" {code}" if code is not None else ""
        super().__init__(f"Binance API error{code_label}: {message}")


class BinanceService:
    def __init__(self, api_key: str = "", api_secret: str = "") -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.public_base_url = "https://fapi.binance.com"
        self.base_url = (
            "https://testnet.binancefuture.com"
            if settings.BINANCE_TESTNET
            else "https://fapi.binance.com"
        )

    def _get(self, path: str, params: dict | None = None) -> dict | list:
        response = httpx.get(f"{self.public_base_url}{path}", params=params, timeout=10)
        response.raise_for_status()
        return response.json()

    def _signed_request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        base_url: str | None = None,
    ) -> dict | list:
        if not self.api_key or not self.api_secret:
            raise ValueError("API key and secret are required for signed requests")
        payload = {**(params or {}), "timestamp": int(time.time() * 1000), "recvWindow": 5000}
        query = urlencode(payload)
        signature = hmac.new(self.api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
        response = httpx.request(
            method,
            f"{base_url or self.base_url}{path}?{query}&signature={signature}",
            headers={"X-MBX-APIKEY": self.api_key},
            timeout=15,
        )
        if response.is_error:
            try:
                error = response.json()
            except ValueError:
                error = {}
            raise BinanceAPIError(
                response.status_code,
                error.get("code"),
                error.get("msg") or response.reason_phrase,
            )
        return response.json()

    def fetch_klines(self, symbol: str, interval: str, limit: int = 150) -> list[dict]:
        try:
            rows = self._get(
                "/fapi/v1/klines",
                {"symbol": symbol.upper(), "interval": interval, "limit": limit},
            )
            return [
                {
                    "timestamp": row[0],
                    "close_timestamp": row[6],
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                    "taker_buy_volume": float(row[9]),
                }
                for row in rows
            ]
        except (httpx.HTTPError, ValueError, KeyError):
            return self._mock_klines(symbol, interval, limit)

    def market_metrics(self, symbol: str, period: str = "15m") -> dict:
        statistics_period = {
            "1m": "5m",
            "3m": "5m",
            "4h": "1h",
        }.get(period, period)
        try:
            premium = self._get("/fapi/v1/premiumIndex", {"symbol": symbol})
        except (httpx.HTTPError, ValueError, KeyError):
            return self._mock_metrics(symbol)

        mock = self._mock_metrics(symbol)
        try:
            oi = self._get("/fapi/v1/openInterest", {"symbol": symbol})
            latest_oi = float(oi["openInterest"])
        except (httpx.HTTPError, ValueError, KeyError):
            latest_oi = mock["open_interest"]

        try:
            oi_history = self._get(
                    "/futures/data/openInterestHist",
                    {"symbol": symbol, "period": statistics_period, "limit": 2},
                )
            previous_oi = float(oi_history[-2]["sumOpenInterest"])
            oi_change = ((latest_oi - previous_oi) / previous_oi * 100) if previous_oi else 0
            oi_change_available = True
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            oi_change = 0.0
            oi_change_available = False

        try:
            accounts = self._get(
                    "/futures/data/topLongShortAccountRatio",
                    {"symbol": symbol, "period": statistics_period, "limit": 2},
                )
            account_ratio = float(accounts[-1]["longShortRatio"])
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            account_ratio = 1.0

        try:
            positions = self._get(
                    "/futures/data/topLongShortPositionRatio",
                    {"symbol": symbol, "period": statistics_period, "limit": 2},
                )
            position_ratio = float(positions[-1]["longShortRatio"])
            position_direction = float(positions[-1]["longShortRatio"]) - float(
                positions[-2]["longShortRatio"]
            )
        except (httpx.HTTPError, ValueError, KeyError, IndexError):
            position_ratio = 1.0
            position_direction = 0.0

        return {
            "price": float(premium["markPrice"]),
            "funding_rate": float(premium["lastFundingRate"]),
            "open_interest": latest_oi,
            "open_interest_change_percent": oi_change,
            "open_interest_change_available": oi_change_available,
            "statistics_period": statistics_period,
            "top_trader_account_ratio": account_ratio,
            "top_trader_position_ratio": position_ratio,
            "top_ratio_direction": position_direction,
            "source": "binance",
        }

    def open_interest_history(self, symbol: str, period: str, limit: int = 200) -> list[dict]:
        try:
            rows = self._get(
                "/futures/data/openInterestHist",
                {"symbol": symbol.upper(), "period": period, "limit": limit},
            )
            return [
                {
                    "timestamp": int(row["timestamp"]),
                    "open_interest": float(row["sumOpenInterest"]),
                }
                for row in rows
            ]
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return []

    def mark_price(self, symbol: str) -> Decimal:
        data = self._get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
        return Decimal(str(data["markPrice"]))

    def symbol_rules(self, symbol: str) -> SymbolRules:
        data = self._get("/fapi/v1/exchangeInfo")
        item = next(entry for entry in data["symbols"] if entry["symbol"] == symbol.upper())
        filters = {entry["filterType"]: entry for entry in item["filters"]}
        return SymbolRules(
            tick_size=Decimal(filters["PRICE_FILTER"]["tickSize"]),
            step_size=Decimal(filters["LOT_SIZE"]["stepSize"]),
            min_notional=Decimal(filters["MIN_NOTIONAL"]["notional"]),
        )

    @staticmethod
    def normalize_order(
        price: Decimal,
        quantity: Decimal,
        rules: SymbolRules,
    ) -> tuple[Decimal, Decimal]:
        price = Decimal(str(price))
        quantity = Decimal(str(quantity))
        normalized_price = (price / rules.tick_size).to_integral_value(rounding=ROUND_DOWN) * rules.tick_size
        normalized_quantity = (
            (quantity / rules.step_size).to_integral_value(rounding=ROUND_DOWN) * rules.step_size
        )
        if normalized_price * normalized_quantity < rules.min_notional:
            raise ValueError("Order is below Binance minimum notional")
        return normalized_price, normalized_quantity

    def fetch_top_movers(self, limit: int = 20, quote_asset: str = "USDT") -> dict:
        """Return top gainers and losers from Binance Futures 24hr ticker data."""
        try:
            tickers = self._get("/fapi/v1/ticker/24hr")
        except (httpx.HTTPError, ValueError, KeyError):
            return {"gainers": [], "losers": []}

        filtered = [
            {
                "symbol": t["symbol"],
                "price": float(t["lastPrice"]),
                "price_change_percent": float(t["priceChangePercent"]),
                "price_change": float(t["priceChange"]),
                "high": float(t["highPrice"]),
                "low": float(t["lowPrice"]),
                "volume": float(t["volume"]),
                "quote_volume": float(t["quoteVolume"]),
            }
            for t in tickers
            if isinstance(t, dict)
            and t.get("symbol", "").endswith(quote_asset)
            and t.get("lastPrice")
        ]

        sorted_by_change = sorted(filtered, key=lambda x: x["price_change_percent"], reverse=True)
        gainers = sorted_by_change[:limit]
        losers = sorted_by_change[-limit:][::-1]

        return {"gainers": gainers, "losers": losers}

    def test_connection(self) -> dict:
        if not self.api_key:
            return {"connected": False, "message": "No API key configured"}
        try:
            account = self._signed_request("GET", "/fapi/v2/account")
            permissions = self.api_permissions()
            futures_enabled = bool(permissions.get("enableFutures"))
            can_trade = bool(account.get("canTrade")) and futures_enabled
            return {
                "connected": True,
                "message": (
                    "Binance Futures credential verified"
                    if can_trade
                    else "Credential is readable, but Enable Futures trading is disabled for this API key"
                ),
                "can_trade": can_trade,
                "futures_enabled": futures_enabled,
                "ip_restricted": bool(permissions.get("ipRestrict")),
            }
        except (httpx.HTTPError, BinanceAPIError) as exc:
            return {"connected": False, "message": str(exc)}

    def api_permissions(self) -> dict:
        if settings.BINANCE_TESTNET:
            return {"enableFutures": True, "ipRestrict": False}
        return self._signed_request(
            "GET",
            "/sapi/v1/account/apiRestrictions",
            base_url="https://api.binance.com",
        )

    def account_balance(self, asset: str = "USDT") -> float:
        balances = self._signed_request("GET", "/fapi/v2/balance")
        item = next(row for row in balances if row["asset"] == asset)
        return float(item["availableBalance"])

    def set_leverage(self, symbol: str, leverage: int) -> dict:
        return self._signed_request(
            "POST",
            "/fapi/v1/leverage",
            {"symbol": symbol.upper(), "leverage": leverage},
        )

    def set_margin_type(self, symbol: str, margin_type: str) -> dict:
        try:
            return self._signed_request(
                "POST",
                "/fapi/v1/marginType",
                {"symbol": symbol.upper(), "marginType": margin_type.upper()},
            )
        except BinanceAPIError as exc:
            if exc.code == -4046:
                return {"status": "unchanged"}
            raise

    def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        reduce_only: bool = False,
    ) -> dict:
        return self._signed_request(
            "POST",
            "/fapi/v1/order",
            {
                "symbol": symbol.upper(),
                "side": side,
                "type": "MARKET",
                "quantity": format(quantity, "f"),
                "reduceOnly": str(reduce_only).lower(),
                "newOrderRespType": "RESULT",
            },
        )

    def place_close_algo_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        trigger_price: Decimal,
        client_algo_id: str,
        quantity: Decimal | None = None,
        close_position: bool = False,
    ) -> dict:
        params = {
            "algoType": "CONDITIONAL",
            "symbol": symbol.upper(),
            "side": side,
            "positionSide": "BOTH",
            "type": order_type,
            "triggerPrice": format(trigger_price, "f"),
            "workingType": "MARK_PRICE",
            "priceProtect": "false",
            "clientAlgoId": client_algo_id,
        }
        if close_position:
            params["closePosition"] = "true"
        elif quantity is not None:
            params["quantity"] = format(quantity, "f")
            params["reduceOnly"] = "true"
        else:
            raise ValueError("Protective order requires quantity or close_position=True")
        return self._signed_request("POST", "/fapi/v1/algoOrder", params)

    def cancel_all_algo_orders(self, symbol: str) -> dict:
        return self._signed_request(
            "DELETE",
            "/fapi/v1/algoOpenOrders",
            {"symbol": symbol.upper()},
        )

    def position_amount(self, symbol: str) -> Decimal:
        rows = self._signed_request(
            "GET",
            "/fapi/v2/positionRisk",
            {"symbol": symbol.upper()},
        )
        position = next(
            (row for row in rows if row["symbol"] == symbol.upper()),
            None,
        )
        return abs(Decimal(position["positionAmt"])) if position else Decimal("0")

    def position_unrealized_pnl(self, symbol: str) -> Decimal:
        rows = self._signed_request(
            "GET",
            "/fapi/v2/positionRisk",
            {"symbol": symbol.upper()},
        )
        position = next((row for row in rows if row["symbol"] == symbol.upper()), None)
        if not position:
            return Decimal("0")
        return Decimal(str(position.get("unRealizedProfit", "0")))

    def user_trades(self, symbol: str, start_time_ms: int, limit: int = 200) -> list[dict]:
        """Fetch actual trade fills for a symbol since start_time_ms."""
        return self._signed_request(
            "GET",
            "/fapi/v1/userTrades",
            {"symbol": symbol.upper(), "startTime": start_time_ms, "limit": limit},
        )

    @staticmethod
    def _mock_klines(symbol: str, interval: str, limit: int) -> list[dict]:
        seed = sum(ord(char) for char in f"{symbol}:{interval}")
        rng = random.Random(seed + int(time.time() // 300))
        base = 64000 if "BTC" in symbol else 25 if "ZEC" not in symbol else 420
        candles = []
        price = float(base)
        interval_ms = {
            "1m": 60_000,
            "3m": 180_000,
            "5m": 300_000,
            "15m": 900_000,
            "30m": 1_800_000,
            "1h": 3_600_000,
            "4h": 14_400_000,
        }.get(interval, 900_000)
        now = int(time.time() * 1000)
        for index in range(limit):
            drift = math.sin(index / 13) * base * 0.0007 + base * 0.00012
            close = max(0.0001, price + drift + rng.gauss(0, base * 0.0018))
            high = max(price, close) + abs(rng.gauss(0, base * 0.0008))
            low = min(price, close) - abs(rng.gauss(0, base * 0.0008))
            volume = abs(rng.gauss(1200, 280))
            taker_ratio = min(0.85, max(0.15, 0.5 + (close - price) / max(base * 0.02, 1)))
            candles.append(
                {
                    "timestamp": now - (limit - index) * interval_ms,
                    "close_timestamp": now - (limit - index - 1) * interval_ms - 1,
                    "open": price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "taker_buy_volume": volume * taker_ratio,
                }
            )
            price = close
        return candles

    @staticmethod
    def _mock_metrics(symbol: str) -> dict:
        seed = sum(ord(char) for char in symbol) + int(time.time() // 60)
        rng = random.Random(seed)
        base_price = 64000 if "BTC" in symbol else 420 if "ZEC" in symbol else 0.08
        return {
            "price": base_price * (1 + rng.uniform(-0.004, 0.004)),
            "funding_rate": rng.uniform(-0.0002, 0.00035),
            "open_interest": rng.uniform(800_000, 1_400_000),
            "open_interest_change_percent": rng.uniform(-1.2, 2.4),
            "open_interest_change_available": False,
            "statistics_period": "mock",
            "top_trader_account_ratio": rng.uniform(0.85, 1.35),
            "top_trader_position_ratio": rng.uniform(0.85, 1.35),
            "top_ratio_direction": rng.uniform(-0.05, 0.05),
            "source": "mock",
        }
