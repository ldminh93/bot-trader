from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0021_ma7_slope_and_funding_confirmation"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="min_confidence_to_trade",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Block entries below this confidence score. 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="auto_suppress_losing_symbols",
            field=models.BooleanField(
                default=False,
                help_text="Block entries on this symbol when its last 20+ closed trades have <40% win rate.",
            ),
        ),
    ]
