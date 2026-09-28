# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0043_trade_add_performance_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="short_entry_score_threshold",
            field=models.PositiveSmallIntegerField(
                default=65,
                help_text="SHORT-only override of entry_score_threshold — a higher bar to compensate for "
                "SHORT's worse risk/reward (violent mean-reversion bounces). 0 = same threshold as LONG.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="short_extended_move_lookback_candles",
            field=models.PositiveSmallIntegerField(
                default=40,
                help_text="SHORT-only override of extended_move_lookback_candles. Dumps often take longer "
                "to finish than the shared lookback catches, so SHORT gets a longer window by default. "
                "0 = same lookback as LONG (extended_move_lookback_candles). Does not affect LONG.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="short_extended_move_fresh_extreme_buffer_pct",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=0.3,
                help_text="SHORT-only: a 'fresh low' must undercut the prior low by at least this %% to "
                "count as the dump still actively happening, instead of a marginal stop-hunt wick during "
                "basing. 0 = any lower low counts (old behaviour). Does not affect LONG.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="short_funding_meaningful_threshold",
            field=models.DecimalField(
                max_digits=8,
                decimal_places=6,
                default=0.0003,
                help_text="SHORT-only: funding rate must exceed this (raw decimal, e.g. 0.0003 = 0.03%) to "
                "score as 'crowded long, favours short'. A barely-positive funding rate is normal baseline, "
                "not a squeeze signal. 0 = any positive funding counts (old behaviour). Does not affect LONG.",
            ),
        ),
        migrations.AddField(
            model_name="tradingbotconfig",
            name="short_rsi_oversold_max",
            field=models.DecimalField(
                max_digits=5,
                decimal_places=2,
                default=25,
                help_text="SHORT-only: block new SHORT entries when RSI(14) is at/below this value — an "
                "already-oversold reading means the down move has likely already run its course, the same "
                "setup that tends to bounce into a loss. 0 = disabled. Does not affect LONG.",
            ),
        ),
    ]
