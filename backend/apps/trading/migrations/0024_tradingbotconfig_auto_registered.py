from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0023_auto_scanner_settings"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="auto_registered",
            field=models.BooleanField(
                default=False,
                help_text="True if this config was created by the top-movers auto-scanner (eligible for sync removal).",
            ),
        ),
    ]
