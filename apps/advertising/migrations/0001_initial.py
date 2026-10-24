import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("media_library", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Advertisement",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=160)),
                (
                    "placement",
                    models.CharField(
                        choices=[
                            ("home", "Accueil"),
                            ("ticketing", "Billetterie"),
                            ("both", "Accueil et billetterie"),
                        ],
                        db_index=True,
                        default="both",
                        max_length=16,
                    ),
                ),
                ("display_delay_seconds", models.PositiveIntegerField(default=10)),
                ("dismissal_cooldown_hours", models.PositiveIntegerField(default=24)),
                ("button_label", models.CharField(default="Acheter maintenant", max_length=80)),
                ("button_url", models.CharField(default="/billetterie", max_length=500)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                (
                    "image",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="advertisements",
                        to="media_library.mediaasset",
                    ),
                ),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
