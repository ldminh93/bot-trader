from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("trading", "0022_min_confidence_and_symbol_suppression"),
    ]

    operations = [
        migrations.CreateModel(
            name="AutoScannerSettings",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("enabled", models.BooleanField(default=False)),
                (
                    "top_n",
                    models.PositiveSmallIntegerField(
                        default=5,
                        help_text="Number of top gainers and top losers to auto-register per run.",
                    ),
                ),
                ("quote_asset", models.CharField(default="USDT", max_length=12)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="auto_scanner_settings",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
