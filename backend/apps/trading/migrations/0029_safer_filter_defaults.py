# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0028_autoscannersettings_last_synced_at"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="require_confirmed_higher_tf",
            field=models.BooleanField(
                default=True,
                help_text="Require higher TF to be CONFIRMED_UPTREND/DOWNTREND (not weak/early). Blocks entries on weak trends.",
            ),
        ),
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="require_ma7_slope_confirmation",
            field=models.BooleanField(
                default=True,
                help_text="Require MA7 slope to point in the trade direction. Blocks entries where MA7 has flattened or turned against the trade.",
            ),
        ),
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="require_funding_confirmation",
            field=models.BooleanField(
                default=True,
                help_text="Require funding rate to be within the acceptable band. Blocks entries into crowded/overheated funding.",
            ),
        ),
    ]
