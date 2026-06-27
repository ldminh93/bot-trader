from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0009_trade_journal_and_entry_filters"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="auto_regime_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="confidence_leverage_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="trade",
            name="replay_payload",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
