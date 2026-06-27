from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("trading", "0010_execution_profile_and_replay"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserDiscordAlertConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("webhook_url_encrypted", models.TextField(blank=True)),
                ("is_enabled", models.BooleanField(default=False)),
                ("notify_info", models.BooleanField(default=True)),
                ("notify_warning", models.BooleanField(default=True)),
                ("notify_error", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="discord_alert_config",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
    ]
