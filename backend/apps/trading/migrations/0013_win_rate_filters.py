from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0012_entry_control_and_error_escalation"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="atr_min_percent",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=6,
                help_text="Minimum ATR as % of price. 0 disables the filter.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="require_4h_alignment",
            field=models.BooleanField(
                default=False,
                help_text="Require 4H trend to align with the signal before entering.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="auto_suppress_losing_tags",
            field=models.BooleanField(
                default=False,
                help_text="Block entries when a setup tag has <40% win rate over 20+ recent trades.",
            ),
        ),
    ]
