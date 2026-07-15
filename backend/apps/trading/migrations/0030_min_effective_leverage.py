# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0029_safer_filter_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="min_effective_leverage",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Minimum leverage when confidence scaling is active. 0 = no floor (allow full scaling).",
            ),
        ),
    ]
