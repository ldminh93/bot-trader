from django.db import migrations


def resync_grade_d(apps, schema_editor):
    """Top-movers auto-sync created coins with allow_grade_d_entries=True even
    after the operator turned it off account-wide. The setting defaults to
    True and is only ever switched off deliberately, so any coin with it off
    is the account's real choice: apply it to every coin of that user."""
    TradingBotConfig = apps.get_model("trading", "TradingBotConfig")
    user_ids = (
        TradingBotConfig.objects.filter(allow_grade_d_entries=False)
        .values_list("user_id", flat=True)
        .distinct()
    )
    TradingBotConfig.objects.filter(user_id__in=list(user_ids)).update(allow_grade_d_entries=False)


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0049_allow_grade_d_entries"),
    ]

    operations = [
        migrations.RunPython(resync_grade_d, migrations.RunPython.noop),
    ]
