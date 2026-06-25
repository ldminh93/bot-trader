from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BotLog, MarketSnapshot, Trade, TradingBotConfig, UserBinanceCredential
from .serializers import (
    BotLogSerializer,
    CredentialSerializer,
    MarketSnapshotSerializer,
    TradeSerializer,
    TradingBotConfigSerializer,
)
from .services.binance_service import BinanceService
from .services.credential_service import decrypt_secret, encrypt_secret
from .services.market_snapshot_service import collect_market_snapshot


def get_config(user, symbol: str | None = None) -> TradingBotConfig:
    requested = (symbol or "BTCUSDT").upper()
    config, _ = TradingBotConfig.objects.get_or_create(user=user, symbol=requested)
    return config


class BotConfigView(APIView):
    def get(self, request):
        symbol = request.query_params.get("symbol")
        if symbol:
            return Response(TradingBotConfigSerializer(get_config(request.user, symbol)).data)
        configs = TradingBotConfig.objects.filter(user=request.user).order_by("symbol")
        return Response(TradingBotConfigSerializer(configs, many=True).data)

    def post(self, request):
        symbol = str(request.data.get("symbol", "")).strip().upper()
        symbol_serializer = TradingBotConfigSerializer(data={"symbol": symbol})
        symbol_serializer.is_valid(raise_exception=True)
        symbol = symbol_serializer.validated_data["symbol"]

        existing = TradingBotConfig.objects.filter(user=request.user, symbol=symbol).first()
        if existing:
            return Response(TradingBotConfigSerializer(existing).data)

        source_symbol = str(request.data.get("copy_from_symbol", "")).strip().upper()
        source = TradingBotConfig.objects.filter(
            user=request.user,
            symbol=source_symbol,
        ).first()
        defaults = {}
        if source:
            copy_fields = (
                "timeframe_signal",
                "timeframe_trend",
                "leverage",
                "margin_type",
                "risk_per_trade_percent",
                "max_daily_loss_percent",
                "max_open_positions",
                "adx_min",
                "atr_multiplier_sl",
                "atr_multiplier_tp",
                "use_trailing_stop",
                "trailing_atr_multiplier",
                "enable_long",
                "enable_short",
                "live_mode_requested",
                "paper_balance",
                "position_margin_usdt",
            )
            defaults = {field: getattr(source, field) for field in copy_fields}
        account_live_mode = TradingBotConfig.objects.filter(
            user=request.user,
            live_mode_requested=True,
        ).exists()
        defaults["live_mode_requested"] = account_live_mode
        defaults["is_running"] = bool(request.data.get("start_scanning", False))
        config = TradingBotConfig.objects.create(
            user=request.user,
            symbol=symbol,
            **defaults,
        )
        BotLog.objects.create(
            user=request.user,
            symbol=symbol,
            message="Coin added to scanner." if config.is_running else "Coin configuration added.",
        )
        return Response(
            TradingBotConfigSerializer(config).data,
            status=status.HTTP_201_CREATED,
        )

    def put(self, request):
        config = get_config(request.user, request.data.get("symbol"))
        serializer = TradingBotConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("live_mode_requested") and not settings.ENABLE_LIVE_TRADING:
            return Response(
                {"detail": "Live trading is disabled by the server environment."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        saved_config = serializer.save()
        if "live_mode_requested" in serializer.validated_data:
            TradingBotConfig.objects.filter(user=request.user).exclude(
                pk=saved_config.pk
            ).update(live_mode_requested=saved_config.live_mode_requested)
        if "max_open_positions" in serializer.validated_data:
            TradingBotConfig.objects.filter(user=request.user).exclude(
                pk=saved_config.pk
            ).update(max_open_positions=saved_config.max_open_positions)
        return Response(serializer.data)

    def delete(self, request):
        symbol = str(
            request.query_params.get("symbol") or request.data.get("symbol") or ""
        ).strip().upper()
        config = TradingBotConfig.objects.filter(user=request.user, symbol=symbol).first()
        if not config:
            return Response(
                {"detail": "Coin configuration not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        config.delete()
        BotLog.objects.create(
            user=request.user,
            symbol=symbol,
            message="Coin removed from scanner.",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class BotStartView(APIView):
    def post(self, request):
        config = get_config(request.user, request.data.get("symbol"))
        config.is_running = True
        config.save(update_fields=["is_running", "updated_at"])
        BotLog.objects.create(user=request.user, symbol=config.symbol, message="Bot started.")
        return Response(TradingBotConfigSerializer(config).data)


class BotStopView(APIView):
    def post(self, request):
        config = get_config(request.user, request.data.get("symbol"))
        config.is_running = False
        config.save(update_fields=["is_running", "updated_at"])
        BotLog.objects.create(user=request.user, symbol=config.symbol, message="Bot stopped.")
        return Response(TradingBotConfigSerializer(config).data)


class MarketSnapshotView(APIView):
    def get(self, request):
        symbol = request.query_params.get("symbol", "BTCUSDT").upper()
        config = get_config(request.user, symbol)
        snapshot = MarketSnapshot.objects.filter(
            symbol=symbol,
            timeframe=config.timeframe_signal,
        ).first()
        stale_before = timezone.now() - timedelta(seconds=10)
        if not snapshot or snapshot.created_at < stale_before:
            snapshot = collect_market_snapshot(config).snapshot
        data = MarketSnapshotSerializer(snapshot).data
        payload = data.setdefault("payload", {})
        legacy_state_map = {
            "UP": "CONFIRMED_UPTREND",
            "DOWN": "CONFIRMED_DOWNTREND",
            "SIDEWAYS": "SIDEWAY",
        }
        trend_state = payload.get("trend_state") or legacy_state_map.get(
            data.get("trend"),
            data.get("trend", "SIDEWAY"),
        )
        payload["trend_state"] = trend_state
        payload["trend_1h"] = legacy_state_map.get(
            payload.get("trend_1h"),
            payload.get("trend_1h", "SIDEWAY"),
        )
        payload.setdefault("signal", "NO_TRADE")
        payload.setdefault("long_score", 0)
        payload.setdefault("short_score", 0)
        payload.setdefault("risk_multiplier", 0)
        payload.setdefault("reasons", ["Waiting for a current strategy snapshot"])
        payload.setdefault("candles", [])
        history = MarketSnapshot.objects.filter(
            symbol=symbol,
            timeframe=config.timeframe_signal,
        ).order_by("-created_at")[:120]
        data["payload"]["market_history"] = [
            {
                "created_at": item.created_at.isoformat(),
                "price": float(item.price),
                "open_interest": float(item.open_interest),
                "funding_rate": float(item.funding_rate),
            }
            for item in reversed(list(history))
        ]
        return Response(data)


class TradesView(APIView):
    def get(self, request):
        trades = Trade.objects.filter(user=request.user)
        symbol = request.query_params.get("symbol")
        if symbol:
            trades = trades.filter(symbol=symbol.upper())
        return Response(TradeSerializer(trades[:200], many=True).data)


class TradeStatsView(APIView):
    def get(self, request):
        closed = Trade.objects.filter(user=request.user, status=Trade.Status.CLOSED)
        totals = closed.aggregate(
            realized_pnl=Sum("realized_pnl"),
            trades=Count("id"),
            average_pnl_percent=Avg("pnl_percent"),
        )
        wins = closed.filter(realized_pnl__gt=0).count()
        total = totals["trades"] or 0
        daily = list(
            closed.annotate(day=TruncDate("closed_at"))
            .values("day")
            .annotate(pnl=Sum("realized_pnl"))
            .order_by("day")
        )
        open_pnl = (
            Trade.objects.filter(user=request.user, status=Trade.Status.OPEN).aggregate(
                value=Sum("unrealized_pnl")
            )["value"]
            or 0
        )
        return Response(
            {
                "realized_pnl": totals["realized_pnl"] or 0,
                "unrealized_pnl": open_pnl,
                "total_profit": (totals["realized_pnl"] or 0) + open_pnl,
                "trades": total,
                "win_rate": (wins / total * 100) if total else 0,
                "average_pnl_percent": totals["average_pnl_percent"] or 0,
                "daily": daily,
            }
        )


class LogsView(APIView):
    def get(self, request):
        logs = BotLog.objects.filter(user=request.user)
        return Response(BotLogSerializer(logs[:200], many=True).data)


class CredentialView(APIView):
    def post(self, request):
        serializer = CredentialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        credential, _ = UserBinanceCredential.objects.update_or_create(
            user=request.user,
            defaults={
                "api_key": data["api_key"],
                "api_secret_encrypted": encrypt_secret(data["api_secret"]),
                "is_active": data["is_active"],
            },
        )
        return Response(
            {
                "id": credential.id,
                "api_key_masked": f"{credential.api_key[:4]}...{credential.api_key[-4:]}",
                "is_active": credential.is_active,
            },
            status=status.HTTP_201_CREATED,
        )


class ConnectionTestView(APIView):
    def get(self, request):
        credential = UserBinanceCredential.objects.filter(user=request.user, is_active=True).first()
        if not credential:
            return Response({"connected": False, "message": "No active credential"}, status=404)
        try:
            secret = decrypt_secret(credential.api_secret_encrypted)
        except ValueError:
            return Response(
                {
                    "connected": False,
                    "message": (
                        "Stored Binance credential was encrypted with a different key. "
                        "Save the API key and secret again."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        service = BinanceService(credential.api_key, secret)
        return Response(service.test_connection())


class SystemStatusView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response(
            {
                "status": "ok",
                "paper_trading": True,
                "live_trading_enabled": settings.ENABLE_LIVE_TRADING,
                "binance_testnet": settings.BINANCE_TESTNET,
            }
        )
