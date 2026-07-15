# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0030_min_effective_leverage"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="block_choppy_entries",
            field=models.BooleanField(
                default=False,
                help_text="Block new entries when the calculated regime is CHOPPY or PULLBACK (signal TF is sideways or weakening).",
            ),
        ),
    ]
