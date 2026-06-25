from django.db import migrations, models


def increase_single_position_limits(apps, schema_editor):
    config_model = apps.get_model("trading", "TradingBotConfig")
    config_model.objects.filter(max_open_positions=1).update(max_open_positions=5)


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0005_tradingbotconfig_position_margin_usdt"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="max_open_positions",
            field=models.PositiveSmallIntegerField(default=5),
        ),
        migrations.RunPython(
            increase_single_position_limits,
            migrations.RunPython.noop,
        ),
    ]
