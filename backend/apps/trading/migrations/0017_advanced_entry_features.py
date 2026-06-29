from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0016_entry_filters"),
    ]

    operations = [
        # TradingBotConfig: partial entry scaling
        migrations.AddField(
            model_name="tradingbotconfig",
            name="partial_entry_enabled",
            field=models.BooleanField(
                default=False,
                help_text="Enter at partial_entry_size_pct% first; scale in the rest when price confirms above/below MA7.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="partial_entry_size_pct",
            field=models.DecimalField(
                decimal_places=2, default=50, max_digits=5,
                help_text="Percentage of planned quantity to enter initially. Rest added on confirmation.",
            ),
        ),
        # TradingBotConfig: circuit breaker
        migrations.AddField(
            model_name="tradingbotconfig",
            name="max_consecutive_losses",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Pause new entries after N consecutive losses on this symbol. 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="circuit_breaker_hours",
            field=models.DecimalField(
                decimal_places=1, default=4, max_digits=4,
                help_text="Hours to block new entries after hitting max_consecutive_losses.",
            ),
        ),
        # TradingBotConfig: volume spike
        migrations.AddField(
            model_name="tradingbotconfig",
            name="volume_spike_multiplier",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=4,
                help_text="Require signal candle volume >= N × volume MA20. 0 = disabled.",
            ),
        ),
        # TradingBotConfig: MA slope filter
        migrations.AddField(
            model_name="tradingbotconfig",
            name="ma_slope_min_pct",
            field=models.DecimalField(
                decimal_places=4, default=0, max_digits=6,
                help_text="Minimum MA7 slope (% per candle over 5 bars) in signal direction. 0 = disabled.",
            ),
        ),
        # TradingBotConfig: dynamic TP by ADX
        migrations.AddField(
            model_name="tradingbotconfig",
            name="adx_tp_high_threshold",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="When ADX >= this, widen TP R-multiple by 33%. 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="adx_tp_low_threshold",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="When ADX <= this, narrow TP R-multiple by 33%. 0 = disabled.",
            ),
        ),
        # Trade: partial entry tracking
        migrations.AddField(
            model_name="trade",
            name="partial_entry_filled",
            field=models.BooleanField(
                default=True,
                help_text="False while waiting for scale-in confirmation after a partial entry.",
            ),
        ),
    ]
