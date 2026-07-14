# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0026_tradingbotconfig_top_mover_side_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="early_exit_min_loss_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Early exit is suppressed until margin ROI drops below this negative threshold (e.g. 5 = -5%). 0 = disabled.",
                max_digits=5,
            ),
        ),
    ]
