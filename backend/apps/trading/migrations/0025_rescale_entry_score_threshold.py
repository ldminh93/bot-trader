"""
Migration: rescale entry_score_threshold from the old 0-137 scoring scale
to the new 0-90 scoring scale.

Old system max ≈ 137, old default = 85 (≈ 62% of max).
New system max  =  90, new default = 55 (≈ 61% of max).

Any row still at the old default of 85 is reset to 55.
Rows that were deliberately set above 90 are clamped to 90 (the new max).
Rows intentionally set below 55 keep their value unchanged.
"""
from django.db import migrations, models


def rescale_thresholds(apps, schema_editor):
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    # Reset rows that were never changed from the old default
    TradingBotConfig.objects.filter(entry_score_threshold=85).update(entry_score_threshold=55)
    # Clamp any rows that are now above the new maximum (90)
    for config in TradingBotConfig.objects.filter(entry_score_threshold__gt=90):
        config.entry_score_threshold = 90
        config.save(update_fields=["entry_score_threshold"])


def reverse_rescale(apps, schema_editor):
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(entry_score_threshold=55).update(entry_score_threshold=85)


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0024_tradingbotconfig_auto_registered"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="entry_score_threshold",
            field=models.PositiveSmallIntegerField(default=55),
        ),
        migrations.RunPython(rescale_thresholds, reverse_code=reverse_rescale),
    ]
