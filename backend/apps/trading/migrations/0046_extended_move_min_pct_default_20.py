# Generated migration

from decimal import Decimal

from django.db import migrations, models


def bump_default_to_20(apps, schema_editor):
    """
    Only bump rows still sitting at the old default (10) — a row a user
    already customized away from the default is left untouched.
    """
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(extended_move_min_pct=Decimal("10")).update(
        extended_move_min_pct=Decimal("20")
    )


def revert_default_to_10(apps, schema_editor):
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    TradingBotConfig.objects.filter(extended_move_min_pct=Decimal("20")).update(
        extended_move_min_pct=Decimal("10")
    )


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0045_signal_decision_and_trade_excursion"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingbotconfig",
            name="extended_move_min_pct",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=20,
                help_text="Minimum price move %% over extended_move_lookback_candles that counts as an "
                "already-completed move. If reached and the current candle isn't making a fresh "
                "high/low in that direction, the entry is blocked as chasing a finished move "
                "(e.g. shorting a coin that already dumped and is now just chopping near the low). "
                "Applies to both LONG and SHORT. 0 = disabled.",
            ),
        ),
        migrations.RunPython(bump_default_to_20, revert_default_to_10),
    ]
