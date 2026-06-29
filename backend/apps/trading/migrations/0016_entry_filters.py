from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0015_stepped_stop_loss"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="funding_rate_threshold",
            field=models.DecimalField(
                decimal_places=6,
                default=0,
                max_digits=8,
                help_text="Block LONG when funding > threshold, SHORT when < -threshold (raw decimal, e.g. 0.0005 = 0.05%). 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="sl_cooldown_candles",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Candles to wait before re-entering after a stop loss hit. 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="atr_spike_max_ratio",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=4,
                help_text="Block entry when ATR / ATR_MA20 exceeds this ratio (volatility spike). 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="min_tf_alignment_score",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Minimum number of timeframes (0-3) aligned with signal direction. 0 = disabled.",
            ),
        ),
    ]
