from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("trading", "0047_late_entry_gates"),
    ]

    operations = [
        migrations.AddField(
            model_name="signaldecision",
            name="atr",
            field=models.DecimalField(blank=True, decimal_places=10, max_digits=24, null=True),
        ),
    ]
