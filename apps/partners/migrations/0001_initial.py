import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [("media_library", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="Partner",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("name", models.CharField(max_length=160)),
                ("order", models.PositiveSmallIntegerField(default=1)),
                ("is_visible", models.BooleanField(default=True)),
                ("logo", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="media_library.mediaasset")),
            ],
            options={"ordering": ["order", "name"]},
        ),
    ]