from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0013_win_rate_filters"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="tp3_trailing_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=5,
                help_text="Trailing stop % after TP3 price is reached. 0 = close immediately at TP3.",
            ),
        ),
        migrations.AddField(
            model_name="trade",
            name="tp3_hit",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="trade",
            name="tp3_trail_price",
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=24, null=True),
        ),
    ]
