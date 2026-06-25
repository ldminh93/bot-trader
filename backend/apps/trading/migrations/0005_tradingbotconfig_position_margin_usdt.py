from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0004_recalculate_margin_roi"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="position_margin_usdt",
            field=models.DecimalField(
                blank=True,
                decimal_places=8,
                help_text="Fixed margin allocated to each new position. Null uses risk-based sizing.",
                max_digits=20,
                null=True,
            ),
        ),
    ]
