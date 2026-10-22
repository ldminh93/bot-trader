from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0048_signaldecision_atr"),
    ]

    operations = [
        migrations.AddField(
            model_name="tradingbotconfig",
            name="allow_grade_d_entries",
            field=models.BooleanField(
                default=True,
                help_text="When off, new entries graded D (confidence less than 8 points above the entry "
                "threshold after regime/alignment adjustments) are skipped. Applies to mirrored follower "
                "entries too. Account-wide: applies to every scanner coin, kept in sync across all of a "
                "user's configs.",
            ),
        ),
    ]
