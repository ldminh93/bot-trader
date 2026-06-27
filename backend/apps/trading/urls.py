from django.urls import path

from .views import (
    BacktestView,
    BotClosePositionView,
    BotConfigView,
    BotKillSwitchView,
    BotLiveSyncView,
    BotStartView,
    BotStopView,
    ConnectionTestView,
    CredentialView,
    DiscordAlertConfigView,
    LogsView,
    MarketSnapshotView,
    OpportunityScoreboardView,
    SystemStatusView,
    TradesView,
    TradeStatsView,
)

urlpatterns = [
    path("bot/config", BotConfigView.as_view()),
    path("bot/start", BotStartView.as_view()),
    path("bot/stop", BotStopView.as_view()),
    path("bot/close-position", BotClosePositionView.as_view()),
    path("bot/live-sync", BotLiveSyncView.as_view()),
    path("bot/kill-switch", BotKillSwitchView.as_view()),
    path("bot/backtest", BacktestView.as_view()),
    path("market/snapshot", MarketSnapshotView.as_view()),
    path("market/opportunities", OpportunityScoreboardView.as_view()),
    path("trades", TradesView.as_view()),
    path("trades/stats", TradeStatsView.as_view()),
    path("logs", LogsView.as_view()),
    path("binance/credentials", CredentialView.as_view()),
    path("binance/connection-test", ConnectionTestView.as_view()),
    path("alerts/discord", DiscordAlertConfigView.as_view()),
    path("status", SystemStatusView.as_view()),
]

