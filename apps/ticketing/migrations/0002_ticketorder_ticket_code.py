import secrets

import apps.ticketing.models
from django.db import migrations, models


def populate_ticket_codes(apps, schema_editor):
    TicketOrder = apps.get_model("ticketing", "TicketOrder")
    database = schema_editor.connection.alias
    for order in TicketOrder.objects.using(database).filter(ticket_code__isnull=True).iterator():
        order.ticket_code = f"AT-{secrets.token_hex(6).upper()}"
        order.save(update_fields=["ticket_code"], using=database)


class Migration(migrations.Migration):
    dependencies = [
        ("ticketing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="ticketorder",
            name="ticket_code",
            field=models.CharField(blank=True, max_length=15, null=True),
        ),
        migrations.RunPython(populate_ticket_codes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="ticketorder",
            name="ticket_code",
            field=models.CharField(
                default=apps.ticketing.models.generate_ticket_code,
                editable=False,
                max_length=15,
                unique=True,
            ),
        ),
    ]
