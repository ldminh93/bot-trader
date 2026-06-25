from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0007_ma_based_risk_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="max_margin_loss_percent",
            field=models.DecimalField(decimal_places=2, default=20, max_digits=5),
        ),
    ]
