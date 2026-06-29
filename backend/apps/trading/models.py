from django.contrib.auth import get_user_model
from django.core.validators import MinValueValidator
from django.db import models

User = get_user_model()


class UserBinanceCredential(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="binance_credential")
    api_key = models.CharField(max_length=255)
    api_secret_encrypted = models.TextField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class UserDiscordAlertConfig(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="discord_alert_config")
    webhook_url_encrypted = models.TextField(blank=True)
    is_enabled = models.BooleanField(default=False)
    notify_info = models.BooleanField(default=True)
    notify_warning = models.BooleanField(default=True)
    notify_error = models.BooleanField(default=True)
    error_escalation_enabled = models.BooleanField(default=True)
    error_escalation_threshold = models.PositiveSmallIntegerField(default=3)
    error_escalation_window_minutes = models.PositiveSmallIntegerField(default=15)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class TradingBotConfig(models.Model):
    class MarginType(models.TextChoices):
        ISOLATED = "isolated", "Isolated"
        CROSS = "cross", "Cross"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bot_configs")
    symbol = models.CharField(max_length=24, default="BTCUSDT")
    timeframe_signal = models.CharField(max_length=8, default="15m")
    timeframe_trend = models.CharField(max_length=8, default="1h")
    leverage = models.PositiveSmallIntegerField(default=10)
    margin_type = models.CharField(max_length=12, choices=MarginType.choices, default=MarginType.ISOLATED)
    risk_per_trade_percent = models.DecimalField(max_digits=5, decimal_places=2, default=1)
    max_daily_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, default=3)
    max_margin_loss_percent = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    entry_score_threshold = models.PositiveSmallIntegerField(default=85)
    max_open_positions = models.PositiveSmallIntegerField(default=5)
    adx_min = models.DecimalField(max_digits=6, decimal_places=2, default=20)
    atr_multiplier_sl = models.DecimalField(max_digits=6, decimal_places=2, default=0.25)
    atr_multiplier_tp = models.DecimalField(max_digits=6, decimal_places=2, default=3)
    use_trailing_stop = models.BooleanField(default=True)
    trailing_atr_multiplier = models.DecimalField(max_digits=6, decimal_places=2, default=1.2)
    enable_long = models.BooleanField(default=True)
    enable_short = models.BooleanField(default=True)
    require_trend_alignment = models.BooleanField(default=True)
    require_open_interest_confirmation = models.BooleanField(default=False)
    require_volume_confirmation = models.BooleanField(default=False)
    auto_regime_enabled = models.BooleanField(default=True)
    confidence_leverage_enabled = models.BooleanField(default=True)
    use_closed_candle_confirmation = models.BooleanField(default=True)
    pullback_entry_enabled = models.BooleanField(default=True)
    max_entry_distance_atr = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    is_running = models.BooleanField(default=False)
    live_mode_requested = models.BooleanField(default=False)
    paper_balance = models.DecimalField(max_digits=20, decimal_places=8, default=10000)
    position_margin_usdt = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Fixed margin allocated to each new position. Null uses risk-based sizing.",
    )
    atr_min_percent = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Minimum ATR as % of price. 0 disables the filter.",
    )
    require_4h_alignment = models.BooleanField(
        default=False,
        help_text="Require 4H trend to align with the signal before entering.",
    )
    auto_suppress_losing_tags = models.BooleanField(
        default=False,
        help_text="Block entries when a setup tag has <40% win rate over 20+ recent trades.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "symbol"], name="unique_user_symbol_config")
        ]


class MarketSnapshot(models.Model):
    class Trend(models.TextChoices):
        SIDEWAY = "SIDEWAY", "Sideway"
        EARLY_UPTREND = "EARLY_UPTREND", "Early uptrend"
        CONFIRMED_UPTREND = "CONFIRMED_UPTREND", "Confirmed uptrend"
        WEAK_UPTREND = "WEAK_UPTREND", "Weak uptrend"
        EARLY_DOWNTREND = "EARLY_DOWNTREND", "Early downtrend"
        CONFIRMED_DOWNTREND = "CONFIRMED_DOWNTREND", "Confirmed downtrend"
        WEAK_DOWNTREND = "WEAK_DOWNTREND", "Weak downtrend"

    symbol = models.CharField(max_length=24, db_index=True)
    timeframe = models.CharField(max_length=8)
    price = models.DecimalField(max_digits=24, decimal_places=10)
    ma7 = models.DecimalField(max_digits=24, decimal_places=10, null=True)
    ma25 = models.DecimalField(max_digits=24, decimal_places=10, null=True)
    ma99 = models.DecimalField(max_digits=24, decimal_places=10, null=True)
    delta = models.DecimalField(max_digits=28, decimal_places=10, default=0)
    cvd = models.DecimalField(max_digits=28, decimal_places=10, default=0)
    open_interest = models.DecimalField(max_digits=28, decimal_places=10, default=0)
    open_interest_change_percent = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    funding_rate = models.DecimalField(max_digits=14, decimal_places=10, default=0)
    top_trader_account_ratio = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    top_trader_position_ratio = models.DecimalField(max_digits=14, decimal_places=8, default=0)
    adx = models.DecimalField(max_digits=12, decimal_places=6, null=True)
    atr = models.DecimalField(max_digits=24, decimal_places=10, null=True)
    volume = models.DecimalField(max_digits=28, decimal_places=10, default=0)
    volume_ma20 = models.DecimalField(max_digits=28, decimal_places=10, null=True)
    trend = models.CharField(max_length=24, choices=Trend.choices, default=Trend.SIDEWAY)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class Trade(models.Model):
    class Side(models.TextChoices):
        LONG = "LONG", "Long"
        SHORT = "SHORT", "Short"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"
        CANCELLED = "CANCELLED", "Cancelled"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trades")
    symbol = models.CharField(max_length=24, db_index=True)
    side = models.CharField(max_length=8, choices=Side.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN)
    entry_price = models.DecimalField(max_digits=24, decimal_places=10)
    exit_price = models.DecimalField(max_digits=24, decimal_places=10, null=True, blank=True)
    quantity = models.DecimalField(
        max_digits=24,
        decimal_places=10,
        validators=[MinValueValidator(0)],
    )
    remaining_quantity = models.DecimalField(max_digits=24, decimal_places=10, default=0)
    leverage = models.PositiveSmallIntegerField(default=1)
    stop_loss = models.DecimalField(max_digits=24, decimal_places=10)
    take_profit_1 = models.DecimalField(max_digits=24, decimal_places=10)
    take_profit_2 = models.DecimalField(max_digits=24, decimal_places=10)
    take_profit_3 = models.DecimalField(max_digits=24, decimal_places=10)
    realized_pnl = models.DecimalField(max_digits=24, decimal_places=10, default=0)
    unrealized_pnl = models.DecimalField(max_digits=24, decimal_places=10, default=0)
    pnl_percent = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    fees = models.DecimalField(max_digits=24, decimal_places=10, default=0)
    open_reason = models.TextField()
    close_reason = models.TextField(blank=True)
    setup_tags = models.JSONField(default=list, blank=True)
    replay_payload = models.JSONField(default=dict, blank=True)
    is_paper = models.BooleanField(default=True)
    tp1_hit = models.BooleanField(default=False)
    tp2_hit = models.BooleanField(default=False)
    breakeven_moved = models.BooleanField(default=False)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]


class BotLog(models.Model):
    class Level(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bot_logs")
    symbol = models.CharField(max_length=24)
    level = models.CharField(max_length=12, choices=Level.choices, default=Level.INFO)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
