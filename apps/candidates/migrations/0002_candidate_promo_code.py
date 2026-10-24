from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("candidates", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="candidate",
            name="promo_code",
            field=models.CharField(blank=True, max_length=32, null=True, unique=True),
        ),
    ]
