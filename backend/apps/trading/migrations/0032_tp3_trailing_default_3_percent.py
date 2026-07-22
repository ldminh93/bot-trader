from django.db import migrations, models


def apply_tp3_trailing_default(apps, schema_editor):
    """
    TP3 previously defaulted to closing the position outright (0 = close
    immediately). Existing configs still sitting on that untouched default
    are moved to a 3% trailing stop so TP3 rides the trend instead of
    exiting the whole position; rows a user has already customized are
    left untouched.
    """
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(tp3_trailing_percent=0).update(tp3_trailing_percent=3)


def revert_tp3_trailing_default(apps, schema_editor):
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(tp3_trailing_percent=3).update(tp3_trailing_percent=0)


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0031_block_choppy_entries"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="tp3_trailing_percent",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=3,
                help_text="Trailing stop % after TP3 price is reached. 0 = close immediately at TP3.",
            ),
        ),
        migrations.RunPython(apply_tp3_trailing_default, revert_tp3_trailing_default),
    ]
