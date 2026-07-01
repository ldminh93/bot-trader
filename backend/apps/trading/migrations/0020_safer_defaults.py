from django.db import migrations, models


def apply_safer_defaults(apps, schema_editor):
    """
    Existing configs were created back when these risk controls defaulted to
    off/tight. Bring rows still sitting on the old defaults up to the new
    safer defaults; leave any row a user has already customized untouched.
    """
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(atr_multiplier_sl=0.25).update(atr_multiplier_sl=0.5)
    TradingBotConfig.objects.filter(sl_cooldown_candles=0).update(sl_cooldown_candles=4)
    TradingBotConfig.objects.filter(max_consecutive_losses=0).update(max_consecutive_losses=2)
    TradingBotConfig.objects.filter(auto_suppress_losing_tags=False).update(auto_suppress_losing_tags=True)


def revert_safer_defaults(apps, schema_editor):
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(atr_multiplier_sl=0.5).update(atr_multiplier_sl=0.25)
    TradingBotConfig.objects.filter(sl_cooldown_candles=4).update(sl_cooldown_candles=0)
    TradingBotConfig.objects.filter(max_consecutive_losses=2).update(max_consecutive_losses=0)
    TradingBotConfig.objects.filter(auto_suppress_losing_tags=True).update(auto_suppress_losing_tags=False)


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0019_adx_period"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="atr_multiplier_sl",
            field=models.DecimalField(max_digits=6, decimal_places=2, default=0.5),
        ),
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="sl_cooldown_candles",
            field=models.PositiveSmallIntegerField(
                default=4,
                help_text="Candles to wait before re-entering after a stop loss hit. 0 = disabled.",
            ),
        ),
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="max_consecutive_losses",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="Pause new entries after N consecutive losses on this symbol. 0 = disabled.",
            ),
        ),
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="auto_suppress_losing_tags",
            field=models.BooleanField(
                default=True,
                help_text="Block entries when a setup tag has <40% win rate over 20+ recent trades.",
            ),
        ),
        migrations.RunPython(apply_safer_defaults, revert_safer_defaults),
    ]
