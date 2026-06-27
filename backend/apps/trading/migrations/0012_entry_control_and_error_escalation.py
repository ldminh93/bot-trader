from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0011_discord_alert_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="use_closed_candle_confirmation",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="pullback_entry_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="max_entry_distance_atr",
            field=models.DecimalField(decimal_places=2, default=1, max_digits=6),
        ),
        migrations.AddField(
            model_name="userdiscordalertconfig",
            name="error_escalation_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="userdiscordalertconfig",
            name="error_escalation_threshold",
            field=models.PositiveSmallIntegerField(default=3),
        ),
        migrations.AddField(
            model_name="userdiscordalertconfig",
            name="error_escalation_window_minutes",
            field=models.PositiveSmallIntegerField(default=15),
        ),
    ]
