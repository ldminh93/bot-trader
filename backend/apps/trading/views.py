from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db.models import Avg, Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BotLog, MarketSnapshot, Trade, TradingBotConfig, UserBinanceCredential, UserDiscordAlertConfig
from .serializers import (
    BotLogSerializer,
    CredentialSerializer,
    DiscordAlertConfigSerializer,
    MarketSnapshotSerializer,
    TradeSerializer,
    TradingBotConfigSerializer,
)
from .services.analytics_service import build_trade_analytics
from .services.backtest_service import run_backtest
from .services.binance_service import BinanceService
from .services.credential_service import decrypt_secret, encrypt_secret
from .services.discord_alert_service import send_discord_alert
from .services.discord_alert_service import send_trade_replay_export
from .services.health_service import build_live_sync_health
from .services.live_trading_service import LiveTradingService
from .services.market_snapshot_service import collect_market_snapshot
from .services.opportunity_service import build_opportunity_scoreboard
from .services.paper_trading_service import PaperTradingService


def create_bot_log(user, symbol: str, level: str, message: str) -> BotLog:
    log = BotLog.objects.create(user=user, symbol=symbol, level=level, message=message)
    send_discord_alert(user, symbol, level, message)
    return log


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
                "max_margin_loss_percent",
                "entry_score_threshold",
                "max_open_positions",
                "adx_min",
                "atr_multiplier_sl",
                "atr_multiplier_tp",
                "use_trailing_stop",
                "trailing_atr_multiplier",
                "enable_long",
                "enable_short",
                "require_trend_alignment",
                "require_open_interest_confirmation",
                "require_volume_confirmation",
                "require_confirmed_higher_tf",
                "require_ma7_slope_confirmation",
                "require_funding_confirmation",
                "auto_regime_enabled",
                "confidence_leverage_enabled",
                "use_closed_candle_confirmation",
                "pullback_entry_enabled",
                "max_entry_distance_atr",
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
        create_bot_log(
            user=request.user,
            symbol=symbol,
            level=BotLog.Level.INFO,
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
        create_bot_log(
            user=request.user,
            symbol=symbol,
            level=BotLog.Level.INFO,
            message="Coin removed from scanner.",
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class BotStartView(APIView):
    def post(self, request):
        config = get_config(request.user, request.data.get("symbol"))
        config.is_running = True
        config.save(update_fields=["is_running", "updated_at"])
        create_bot_log(request.user, config.symbol, BotLog.Level.INFO, "Bot started.")
        return Response(TradingBotConfigSerializer(config).data)


class BotStopView(APIView):
    def post(self, request):
        config = get_config(request.user, request.data.get("symbol"))
        config.is_running = False
        config.save(update_fields=["is_running", "updated_at"])
        create_bot_log(request.user, config.symbol, BotLog.Level.INFO, "Bot stopped.")
        return Response(TradingBotConfigSerializer(config).data)


class BotClosePositionView(APIView):
    def post(self, request):
        config = get_config(request.user, request.data.get("symbol"))
        trade = Trade.objects.filter(
            user=request.user,
            symbol=config.symbol,
            status=Trade.Status.OPEN,
        ).first()
        if not trade:
            return Response({"detail": "No open position found."}, status=status.HTTP_404_NOT_FOUND)

        metrics = BinanceService().market_metrics(config.symbol, config.timeframe_signal)
        price = metrics["price"]
        if trade.is_paper:
            PaperTradingService.close_trade(
                trade,
                Decimal(str(price)),
                "Position closed from dashboard",
            )
        else:
            credential = getattr(config.user, "binance_credential", None)
            service = LiveTradingService(credential, config)
            if service.client.position_amount(config.symbol) > 0:
                service.close_trade(
                    trade,
                    Decimal(str(price)),
                    "Position closed from dashboard",
                )
            else:
                service.client.cancel_all_algo_orders(config.symbol)
                PaperTradingService.close_trade(
                    trade,
                    Decimal(str(price)),
                    "Position synced closed from dashboard",
                )
        create_bot_log(
            user=request.user,
            symbol=config.symbol,
            level=BotLog.Level.WARNING,
            message="Position close requested from dashboard.",
        )
        return Response(TradeSerializer(trade).data)


class BotLiveSyncView(APIView):
    def get(self, request):
        return Response(build_live_sync_health(request.user))


class BotKillSwitchView(APIView):
    def post(self, request):
        configs = list(TradingBotConfig.objects.filter(user=request.user))
        TradingBotConfig.objects.filter(user=request.user).update(is_running=False)
        closed = []
        errors = []
        for trade in Trade.objects.filter(user=request.user, status=Trade.Status.OPEN):
            config = next((item for item in configs if item.symbol == trade.symbol), None) or get_config(request.user, trade.symbol)
            try:
                metrics = BinanceService().market_metrics(trade.symbol, config.timeframe_signal)
                price = Decimal(str(metrics["price"]))
                if trade.is_paper:
                    PaperTradingService.close_trade(trade, price, "Kill switch closed paper position")
                else:
                    credential = getattr(request.user, "binance_credential", None)
                    config.live_mode_requested = True
                    service = LiveTradingService(credential, config)
                    if service.client.position_amount(trade.symbol) > 0:
                        service.close_trade(trade, price, "Kill switch closed live position")
                    else:
                        service.client.cancel_all_algo_orders(trade.symbol)
                        PaperTradingService.close_trade(trade, price, "Kill switch synced already-closed live position")
                closed.append(trade.symbol)
            except Exception as exc:
                errors.append({"symbol": trade.symbol, "detail": str(exc)})
                create_bot_log(request.user, trade.symbol, BotLog.Level.ERROR, f"Kill switch failed to close position: {exc}")
        create_bot_log(
            request.user,
            "ALL",
            BotLog.Level.WARNING,
            f"Kill switch executed. Stopped {len(configs)} bots and closed {len(closed)} open positions.",
        )
        return Response({"stopped": len(configs), "closed": closed, "errors": errors})


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
        payload.setdefault("trend_reasons", [])
        payload.setdefault(
            "higher_timeframe_bias",
            {
                "signal_state": trend_state,
                "higher_state": payload.get("trend_1h", "SIDEWAY"),
                "alignment": "aligned",
                "reasons": [],
            },
        )
        payload.setdefault("regime", "MANUAL")
        payload.setdefault("regime_label", "Manual")
        payload.setdefault("regime_notes", [])
        payload.setdefault("confidence_score", 0)
        payload.setdefault("trade_grade", "D")
        payload.setdefault("opportunity_score", 0)
        payload.setdefault("effective_leverage", config.leverage)
        payload.setdefault("leverage_factor", 1)
        payload.setdefault("tp_r_multiple", float(config.atr_multiplier_tp))
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


class OpportunityScoreboardView(APIView):
    def get(self, request):
        return Response(build_opportunity_scoreboard(request.user))


class TradesView(APIView):
    def get(self, request):
        trades = Trade.objects.filter(user=request.user)
        symbol = request.query_params.get("symbol")
        if symbol:
            trades = trades.filter(symbol=symbol.upper())
        return Response(TradeSerializer(trades[:200], many=True).data)


class TradeReplayExportView(APIView):
    def post(self, request):
        trade_id = request.data.get("trade_id")
        trade = Trade.objects.filter(user=request.user, id=trade_id).first()
        if not trade:
            return Response({"detail": "Trade not found."}, status=status.HTTP_404_NOT_FOUND)
        if trade.status != Trade.Status.CLOSED:
            return Response({"detail": "Only closed trades can be exported."}, status=status.HTTP_400_BAD_REQUEST)
        sent = send_trade_replay_export(trade, force=True)
        if not sent:
            return Response({"detail": "Discord webhook is not configured or export failed."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Trade replay exported to Discord."})


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
        # Drawdown from peak balance
        config = TradingBotConfig.objects.filter(user=request.user).first()
        starting_balance = float(config.paper_balance) if config else 10000.0
        current_balance = starting_balance + float(totals["realized_pnl"] or 0) + float(open_pnl)
        running = starting_balance
        peak_balance = running
        for day_item in daily:
            running += float(day_item["pnl"])
            if running > peak_balance:
                peak_balance = running
        peak_balance = max(peak_balance, current_balance)
        drawdown_pct = max(0.0, (peak_balance - current_balance) / peak_balance * 100) if peak_balance > 0 else 0.0
        return Response(
            {
                "realized_pnl": totals["realized_pnl"] or 0,
                "unrealized_pnl": open_pnl,
                "total_profit": (totals["realized_pnl"] or 0) + open_pnl,
                "trades": total,
                "win_rate": (wins / total * 100) if total else 0,
                "average_pnl_percent": totals["average_pnl_percent"] or 0,
                "current_balance": current_balance,
                "peak_balance": peak_balance,
                "drawdown_pct": drawdown_pct,
                "daily": daily,
                "analytics": build_trade_analytics(request.user),
                "block_reasons": build_block_reason_stats(request.user),
            }
        )


class BacktestView(APIView):
    def post(self, request):
        config = get_config(request.user, request.data.get("symbol"))
        limit = int(request.data.get("limit", 320))
        return Response(run_backtest(config, limit=max(180, min(limit, 500))))


class LogsView(APIView):
    def get(self, request):
        logs = BotLog.objects.filter(user=request.user)
        return Response(BotLogSerializer(logs[:200], many=True).data)


def build_block_reason_stats(user) -> list[dict]:
    symbols = list(TradingBotConfig.objects.filter(user=user).values_list("symbol", flat=True))
    since = timezone.now() - timedelta(days=7)
    snapshots = MarketSnapshot.objects.filter(symbol__in=symbols, created_at__gte=since).only("payload", "symbol", "created_at")[:1000]
    buckets: dict[str, dict] = {}
    for snapshot in snapshots:
        payload = snapshot.payload or {}
        if payload.get("signal") != "NO_TRADE":
            continue
        for reason in payload.get("reasons", [])[:4]:
            label = str(reason)[:120]
            item = buckets.setdefault(label, {"reason": label, "count": 0, "symbols": set(), "last_seen": snapshot.created_at})
            item["count"] += 1
            item["symbols"].add(snapshot.symbol)
            if snapshot.created_at > item["last_seen"]:
                item["last_seen"] = snapshot.created_at
    rows = sorted(buckets.values(), key=lambda item: item["count"], reverse=True)[:15]
    return [
        {
            "reason": item["reason"],
            "count": item["count"],
            "symbols": sorted(item["symbols"])[:8],
            "last_seen": item["last_seen"].isoformat(),
        }
        for item in rows
    ]


class DiscordAlertConfigView(APIView):
    def get(self, request):
        config, _ = UserDiscordAlertConfig.objects.get_or_create(user=request.user)
        return Response(DiscordAlertConfigSerializer(config).data)

    def put(self, request):
        config, _ = UserDiscordAlertConfig.objects.get_or_create(user=request.user)
        serializer = DiscordAlertConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        webhook_url = serializer.validated_data.pop("webhook_url", None)
        saved = serializer.save()
        if webhook_url is not None:
            had_webhook = bool(saved.webhook_url_encrypted)
            saved.webhook_url_encrypted = encrypt_secret(webhook_url.strip()) if webhook_url.strip() else ""
            update_fields = ["webhook_url_encrypted", "updated_at"]
            # Auto-enable alerts when a webhook URL is configured for the first time
            if not had_webhook and saved.webhook_url_encrypted and not saved.is_enabled:
                saved.is_enabled = True
                update_fields.append("is_enabled")
            saved.save(update_fields=update_fields)
        return Response(DiscordAlertConfigSerializer(saved).data)

    def post(self, request):
        config, _ = UserDiscordAlertConfig.objects.get_or_create(user=request.user)
        if not config.webhook_url_encrypted:
            return Response({"detail": "Discord webhook is not configured."}, status=status.HTTP_400_BAD_REQUEST)
        send_discord_alert(request.user, "SYSTEM", BotLog.Level.INFO, "Discord alert test from Bot Trader.", force=True)
        return Response({"message": "Discord test alert sent."})


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


class BinanceBalanceView(APIView):
    def get(self, request):
        credential = UserBinanceCredential.objects.filter(user=request.user, is_active=True).first()
        if not credential:
            return Response({"detail": "No active Binance credential"}, status=status.HTTP_404_NOT_FOUND)
        try:
            secret = decrypt_secret(credential.api_secret_encrypted)
        except ValueError:
            return Response(
                {
                    "detail": (
                        "Stored Binance credential was encrypted with a different key. "
                        "Save the API key and secret again."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        service = BinanceService(credential.api_key, secret)
        try:
            balance = service.account_balance()
        except Exception:
            return Response(
                {"detail": "Could not fetch balance from Binance."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return Response({"balance": balance})


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
