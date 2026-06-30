from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0017_advanced_entry_features"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="early_exit_min_conditions",
            field=models.PositiveSmallIntegerField(
                default=3,
                help_text="Conditions needed to trigger early exit (was hardcoded 2). Higher = less sensitive.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="early_exit_grace_candles",
            field=models.PositiveSmallIntegerField(
                default=2,
                help_text="Minimum 15m candles to wait after entry before early exit is allowed. 0 = no grace.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="require_confirmed_higher_tf",
            field=models.BooleanField(
                default=False,
                help_text="Require higher TF to be CONFIRMED_UPTREND/DOWNTREND. Blocks entries on weak/early trends.",
            ),
        ),
    ]
