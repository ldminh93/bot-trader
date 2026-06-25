from django.db import migrations, models


def migrate_trend_values(apps, schema_editor):
    snapshot = apps.get_model("trading", "MarketSnapshot")
    snapshot.objects.filter(trend="UP").update(trend="CONFIRMED_UPTREND")
    snapshot.objects.filter(trend="DOWN").update(trend="CONFIRMED_DOWNTREND")
    snapshot.objects.filter(trend="SIDEWAYS").update(trend="SIDEWAY")


class Migration(migrations.Migration):
    dependencies = [
        ("trading", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="marketsnapshot",
            name="trend",
            field=models.CharField(
                choices=[
                    ("SIDEWAY", "Sideway"),
                    ("EARLY_UPTREND", "Early uptrend"),
                    ("CONFIRMED_UPTREND", "Confirmed uptrend"),
                    ("WEAK_UPTREND", "Weak uptrend"),
                    ("EARLY_DOWNTREND", "Early downtrend"),
                    ("CONFIRMED_DOWNTREND", "Confirmed downtrend"),
                    ("WEAK_DOWNTREND", "Weak downtrend"),
                ],
                default="SIDEWAY",
                max_length=24,
            ),
        ),
        migrations.RunPython(migrate_trend_values, migrations.RunPython.noop),
    ]
