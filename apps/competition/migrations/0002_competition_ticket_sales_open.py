from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("competition", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="competition",
            name="ticket_sales_open",
            field=models.BooleanField(default=False),
        ),
    ]
