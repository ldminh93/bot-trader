from django.db import migrations, models


def upgrade_default_leverage(apps, schema_editor):
    config = apps.get_model("trading", "TradingBotConfig")
    config.objects.filter(leverage=3).update(leverage=10)


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0002_alter_marketsnapshot_trend"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="leverage",
            field=models.PositiveSmallIntegerField(default=10),
        ),
        migrations.RunPython(upgrade_default_leverage, migrations.RunPython.noop),
    ]
