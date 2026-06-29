from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0014_tp3_trailing_stop"),
    ]

    operations = [
        # TradingBotConfig: two new strategy settings
        migrations.AddField(
            model_name="tradingbotconfig",
            name="early_breakeven_r",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=4,
                help_text="Move SL halfway to entry when profit reaches this R multiple. 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="lock_profit_r",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=4,
                help_text="Lock in (lock_profit_r − 1) R of profit when price reaches this R multiple. 0 = disabled.",
            ),
        ),
        # Trade: initial SL reference + step flags
        migrations.AddField(
            model_name="trade",
            name="initial_stop_loss",
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=24, null=True),
        ),
        migrations.AddField(
            model_name="trade",
            name="early_breakeven_moved",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="trade",
            name="profit_lock_moved",
            field=models.BooleanField(default=False),
        ),
    ]
