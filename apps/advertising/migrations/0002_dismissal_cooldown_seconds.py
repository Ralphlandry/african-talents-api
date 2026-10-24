from django.db import migrations, models


def convert_hours_to_seconds(apps, schema_editor):
    Advertisement = apps.get_model("advertising", "Advertisement")
    Advertisement.objects.all().update(
        dismissal_cooldown_hours=models.F("dismissal_cooldown_hours") * 3600
    )


def convert_seconds_to_hours(apps, schema_editor):
    Advertisement = apps.get_model("advertising", "Advertisement")
    Advertisement.objects.all().update(
        dismissal_cooldown_hours=models.F("dismissal_cooldown_hours") / 3600
    )


class Migration(migrations.Migration):
    dependencies = [
        ("advertising", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(convert_hours_to_seconds, convert_seconds_to_hours),
        migrations.RenameField(
            model_name="advertisement",
            old_name="dismissal_cooldown_hours",
            new_name="dismissal_cooldown_seconds",
        ),
        migrations.AlterField(
            model_name="advertisement",
            name="dismissal_cooldown_seconds",
            field=models.PositiveIntegerField(default=86400),
        ),
    ]
