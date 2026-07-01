from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0018_early_exit_controls"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="adx_period",
            field=models.PositiveSmallIntegerField(
                default=14,
                help_text="Lookback period (candles) used to calculate ADX/ATR. Was hardcoded to 14.",
            ),
        ),
    ]
