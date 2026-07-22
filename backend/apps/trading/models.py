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


class AutoScannerSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="auto_scanner_settings")
    enabled = models.BooleanField(default=False)
    top_n = models.PositiveSmallIntegerField(
        default=5,
        help_text="Number of top gainers and top losers to auto-register per run.",
    )
    quote_asset = models.CharField(max_length=12, default="USDT")
    last_synced_at = models.DateTimeField(null=True, blank=True)
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
    entry_score_threshold = models.PositiveSmallIntegerField(default=55)
    max_open_positions = models.PositiveSmallIntegerField(default=5)
    adx_min = models.DecimalField(max_digits=6, decimal_places=2, default=20)
    adx_period = models.PositiveSmallIntegerField(
        default=14,
        help_text="Lookback period (candles) used to calculate ADX/ATR. Was hardcoded to 14.",
    )
    atr_multiplier_sl = models.DecimalField(max_digits=6, decimal_places=2, default=0.5)
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
    min_effective_leverage = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minimum leverage when confidence scaling is active. 0 = no floor (allow full scaling).",
    )
    block_choppy_entries = models.BooleanField(
        default=False,
        help_text="Block new entries when the calculated regime is CHOPPY or PULLBACK (signal TF is sideways or weakening).",
    )
    use_closed_candle_confirmation = models.BooleanField(default=True)
    pullback_entry_enabled = models.BooleanField(default=True)
    max_entry_distance_atr = models.DecimalField(max_digits=6, decimal_places=2, default=1)
    is_running = models.BooleanField(default=False)
    auto_registered = models.BooleanField(
        default=False,
        help_text="True if this config was created by the top-movers auto-scanner (eligible for sync removal).",
    )

    class TopMoverSide(models.TextChoices):
        GAINER = "gainer", "Long (top gainer)"
        LOSER = "loser", "Short (top loser)"

    top_mover_side = models.CharField(
        max_length=8,
        choices=TopMoverSide.choices,
        null=True,
        blank=True,
        help_text="Which top-movers side (gainer/long or loser/short) this coin was registered from. Null for manually added coins.",
    )
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
        default=True,
        help_text="Block entries when a setup tag has <40% win rate over 20+ recent trades.",
    )
    funding_rate_threshold = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        default=0,
        help_text="Block LONG when funding > threshold, SHORT when < -threshold (raw decimal, e.g. 0.0005 = 0.05%). 0 = disabled.",
    )
    sl_cooldown_candles = models.PositiveSmallIntegerField(
        default=4,
        help_text="Candles to wait before re-entering after a stop loss hit. 0 = disabled.",
    )
    atr_spike_max_ratio = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0,
        help_text="Block entry when ATR / ATR_MA20 exceeds this ratio (volatility spike). 0 = disabled.",
    )
    min_tf_alignment_score = models.PositiveSmallIntegerField(
        default=0,
        help_text="Minimum number of timeframes (0-3) aligned with signal direction. 0 = disabled.",
    )
    min_confidence_to_trade = models.PositiveSmallIntegerField(
        default=0,
        help_text="Block entries below this confidence score. 0 = disabled.",
    )
    auto_suppress_losing_symbols = models.BooleanField(
        default=False,
        help_text="Block entries on this symbol when its last 20+ closed trades have <40% win rate.",
    )
    partial_entry_enabled = models.BooleanField(
        default=False,
        help_text="Enter at partial_entry_size_pct% first; scale in the rest when price confirms above/below MA7.",
    )
    partial_entry_size_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=50,
        help_text="Percentage of planned quantity to enter initially (e.g. 50 = half size). Rest added on confirmation.",
    )
    max_consecutive_losses = models.PositiveSmallIntegerField(
        default=2,
        help_text="Pause new entries after N consecutive losses on this symbol. 0 = disabled.",
    )
    circuit_breaker_hours = models.DecimalField(
        max_digits=4, decimal_places=1, default=4,
        help_text="Hours to block new entries after hitting max_consecutive_losses.",
    )
    volume_spike_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=0,
        help_text="Require signal candle volume >= N × volume MA20 (e.g. 2.0). 0 = disabled.",
    )
    ma_slope_min_pct = models.DecimalField(
        max_digits=6, decimal_places=4, default=0,
        help_text="Minimum MA7 slope (% change per candle over 5 bars) in signal direction. 0 = disabled.",
    )
    adx_tp_high_threshold = models.PositiveSmallIntegerField(
        default=0,
        help_text="When ADX ≥ this, widen TP R-multiple by 33%. 0 = disabled.",
    )
    adx_tp_low_threshold = models.PositiveSmallIntegerField(
        default=0,
        help_text="When ADX ≤ this, narrow TP R-multiple by 33%. 0 = disabled.",
    )
    early_exit_min_conditions = models.PositiveSmallIntegerField(
        default=3,
        help_text="Conditions needed to trigger early exit (was hardcoded 2). Higher = less sensitive.",
    )
    early_exit_grace_candles = models.PositiveSmallIntegerField(
        default=2,
        help_text="Minimum 15m candles to wait after entry before early exit is allowed. 0 = no grace.",
    )
    early_exit_min_loss_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Early exit is suppressed until margin ROI drops below this negative threshold (e.g. 5 = -5%). 0 = disabled.",
    )
    require_confirmed_higher_tf = models.BooleanField(
        default=True,
        help_text="Require higher TF to be CONFIRMED_UPTREND/DOWNTREND (not weak/early). Blocks entries on weak trends.",
    )
    require_ma7_slope_confirmation = models.BooleanField(
        default=True,
        help_text="Require MA7 slope to point in the trade direction. Blocks entries where MA7 has flattened or turned against the trade.",
    )
    require_funding_confirmation = models.BooleanField(
        default=True,
        help_text="Require funding rate to be within the acceptable band. Blocks entries into crowded/overheated funding.",
    )
    tp3_trailing_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=3,
        help_text="Trailing stop % after TP3 price is reached. 0 = close immediately at TP3.",
    )
    early_breakeven_r = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0,
        help_text="Move SL halfway to entry when profit reaches this R multiple. 0 = disabled.",
    )
    lock_profit_r = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=0,
        help_text="Lock in (lock_profit_r − 1) R of profit when price reaches this R multiple. 0 = disabled.",
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
    tp3_hit = models.BooleanField(default=False)
    tp3_trail_price = models.DecimalField(max_digits=24, decimal_places=10, null=True, blank=True)
    initial_stop_loss = models.DecimalField(max_digits=24, decimal_places=10, null=True, blank=True)
    early_breakeven_moved = models.BooleanField(default=False)
    breakeven_moved = models.BooleanField(default=False)
    profit_lock_moved = models.BooleanField(default=False)
    partial_entry_filled = models.BooleanField(
        default=True,
        help_text="False while waiting for scale-in confirmation after a partial entry.",
    )
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
