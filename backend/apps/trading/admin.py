from django.contrib import admin

from .models import (
    AutoScannerSettings,
    BotLog,
    MarketSnapshot,
    Trade,
    TradingBotConfig,
    UserBinanceCredential,
    UserDiscordAlertConfig,
)


@admin.register(UserBinanceCredential)
class UserBinanceCredentialAdmin(admin.ModelAdmin):
    list_display = ("user", "is_active", "created_at", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(UserDiscordAlertConfig)
class UserDiscordAlertConfigAdmin(admin.ModelAdmin):
    list_display = (
        "user", "is_enabled", "notify_info", "notify_warning", "notify_error",
        "error_escalation_enabled", "error_escalation_threshold",
    )
    list_filter = ("is_enabled", "error_escalation_enabled")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AutoScannerSettings)
class AutoScannerSettingsAdmin(admin.ModelAdmin):
    list_display = ("user", "enabled", "top_n", "quote_asset", "created_at")
    list_filter = ("enabled", "quote_asset")
    search_fields = ("user__username", "user__email")
    readonly_fields = ("created_at", "updated_at")


@admin.register(TradingBotConfig)
class TradingBotConfigAdmin(admin.ModelAdmin):
    list_display = (
        "user", "symbol", "timeframe_signal", "timeframe_trend",
        "is_running", "live_mode_requested", "leverage", "margin_type",
        "enable_long", "enable_short", "created_at",
    )
    list_filter = (
        "is_running", "live_mode_requested", "margin_type",
        "enable_long", "enable_short", "require_trend_alignment",
        "pullback_entry_enabled", "auto_regime_enabled",
    )
    search_fields = ("user__username", "user__email", "symbol")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Identity", {
            "fields": ("user", "symbol", "timeframe_signal", "timeframe_trend"),
        }),
        ("Mode", {
            "fields": ("is_running", "live_mode_requested", "paper_balance"),
        }),
        ("Position Sizing", {
            "fields": (
                "leverage", "margin_type", "risk_per_trade_percent",
                "position_margin_usdt", "max_open_positions",
            ),
        }),
        ("Risk Limits", {
            "fields": (
                "max_daily_loss_percent", "max_margin_loss_percent",
                "max_consecutive_losses", "circuit_breaker_hours",
            ),
        }),
        ("Stop Loss / Take Profit", {
            "fields": (
                "atr_multiplier_sl", "atr_multiplier_tp",
                "use_trailing_stop", "trailing_atr_multiplier",
                "tp3_trailing_percent", "early_breakeven_r",
                "lock_profit_r", "initial_stop_loss",
                "adx_tp_high_threshold", "adx_tp_low_threshold",
            ),
        }),
        ("Entry Filters", {
            "fields": (
                "entry_score_threshold", "adx_min", "adx_period",
                "enable_long", "enable_short",
                "require_trend_alignment", "require_confirmed_higher_tf",
                "require_4h_alignment", "require_open_interest_confirmation",
                "require_volume_confirmation", "require_ma7_slope_confirmation",
                "require_funding_confirmation",
                "pullback_entry_enabled", "max_entry_distance_atr",
                "atr_min_percent", "atr_spike_max_ratio",
                "volume_spike_multiplier", "ma_slope_min_pct",
                "funding_rate_threshold", "sl_cooldown_candles",
                "min_tf_alignment_score", "min_confidence_to_trade",
            ),
        }),
        ("Smart Features", {
            "fields": (
                "auto_regime_enabled", "confidence_leverage_enabled",
                "use_closed_candle_confirmation",
                "auto_suppress_losing_tags", "auto_suppress_losing_symbols",
                "partial_entry_enabled", "partial_entry_size_pct",
                "early_exit_min_conditions", "early_exit_grace_candles", "early_exit_min_loss_percent",
                "auto_registered",
            ),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )


@admin.register(MarketSnapshot)
class MarketSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "symbol", "timeframe", "trend", "price", "adx", "atr",
        "open_interest", "funding_rate", "created_at",
    )
    list_filter = ("trend", "timeframe", "symbol")
    search_fields = ("symbol",)
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"


@admin.register(Trade)
class TradeAdmin(admin.ModelAdmin):
    list_display = (
        "user", "symbol", "side", "status", "entry_price", "exit_price",
        "quantity", "leverage", "realized_pnl", "pnl_percent",
        "is_paper", "tp1_hit", "tp2_hit", "tp3_hit", "opened_at", "closed_at",
    )
    list_filter = (
        "status", "side", "is_paper", "symbol",
        "tp1_hit", "tp2_hit", "tp3_hit",
    )
    search_fields = ("user__username", "user__email", "symbol", "open_reason", "close_reason")
    readonly_fields = ("opened_at", "closed_at")
    date_hierarchy = "opened_at"


@admin.register(BotLog)
class BotLogAdmin(admin.ModelAdmin):
    list_display = ("user", "symbol", "level", "message", "created_at")
    list_filter = ("level", "symbol")
    search_fields = ("user__username", "user__email", "symbol", "message")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"

