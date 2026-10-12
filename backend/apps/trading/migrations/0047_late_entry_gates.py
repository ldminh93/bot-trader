from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0046_extended_move_min_pct_default_20"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="macro_extension_max_pct",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=10,
                help_text="Block entries when price is already more than this %% away from MA99 in the "
                "trade's direction (LONG: above, SHORT: below) — the trend is mature and the entry is "
                "late, even if price is back at MA25 after consolidating. 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="long_window_move_lookback_candles",
            field=models.PositiveSmallIntegerField(
                default=72,
                help_text="Second, longer lookback for the already-completed-move check (see "
                "long_window_move_min_pct). Catches pumps/dumps that finished too long ago for "
                "extended_move_lookback_candles to see. 0 = disabled.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="long_window_move_min_pct",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=12,
                help_text="Minimum price move %% over long_window_move_lookback_candles that counts as an "
                "already-completed move; same fresh-extreme rule as extended_move_min_pct. 0 = disabled.",
            ),
        ),
    ]
