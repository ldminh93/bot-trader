from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0020_safer_defaults"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="require_ma7_slope_confirmation",
            field=models.BooleanField(
                default=False,
                help_text="Require MA7 slope to point in the trade direction. Blocks entries where MA7 has flattened or turned against the trade.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="require_funding_confirmation",
            field=models.BooleanField(
                default=False,
                help_text="Require funding rate to be within the acceptable band. Blocks entries into crowded/overheated funding.",
            ),
        ),
    ]
