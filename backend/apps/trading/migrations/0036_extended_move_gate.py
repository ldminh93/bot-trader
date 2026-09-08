# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0035_block_sideway_entries"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="extended_move_lookback_candles",
            field=models.PositiveSmallIntegerField(
                default=20,
                help_text="Candles to look back for a big move that already happened before this entry "
                "(see extended_move_min_pct). 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="extended_move_min_pct",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=10,
                help_text="Minimum price move %% over extended_move_lookback_candles that counts as an "
                "already-completed move. If reached and the current candle isn't making a fresh "
                "high/low in that direction, the entry is blocked as chasing a finished move "
                "(e.g. shorting a coin that already dumped and is now just chopping near the low). "
                "0 = disabled.",
            ),
        ),
    ]
