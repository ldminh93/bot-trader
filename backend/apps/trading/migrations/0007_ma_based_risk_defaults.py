from django.db import migrations, models


def update_existing_sl_buffers(apps, schema_editor):
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(atr_multiplier_sl=1.5).update(
        atr_multiplier_sl=0.25
    )


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0006_default_max_open_positions_5"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="atr_multiplier_sl",
            field=models.DecimalField(decimal_places=2, default=0.25, max_digits=6),
        ),
        migrations.RunPython(
            update_existing_sl_buffers,
            migrations.RunPython.noop,
        ),
    ]
