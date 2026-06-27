from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0008_tradingbotconfig_max_margin_loss_percent"),
    ]

    operations = [
        migrations.AddField(
            model_name="trade",
            name="setup_tags",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="entry_score_threshold",
            field=models.PositiveSmallIntegerField(default=85),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="require_open_interest_confirmation",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="require_trend_alignment",
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="require_volume_confirmation",
            field=models.BooleanField(default=False),
        ),
    ]
