# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0034_notify_scanner_changes"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="block_sideway_entries",
            field=models.BooleanField(
                default=True,
                help_text="Skip new entries while the signal-timeframe trend state is SIDEWAY, including the "
                "pullback-recovery path (a recently-confirmed trend that has since cooled to SIDEWAY). "
                "These setups enter close to the anchor MA with a thin stop and have shown a worse win rate.",
            ),
        ),
    ]
