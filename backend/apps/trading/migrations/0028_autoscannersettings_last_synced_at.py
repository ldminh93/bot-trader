# Generated migration

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0027_early_exit_min_loss_percent"),
    ]

    operations = [
        migrations.AddField(
            model_name="autoscannersettings",
            name="last_synced_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
