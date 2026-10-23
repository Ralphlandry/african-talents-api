from django.db import migrations, models


def rename_packages_and_create_basic(apps, schema_editor):
    TicketType = apps.get_model("ticketing", "TicketType")
    Competition = apps.get_model("competition", "Competition")
    database = schema_editor.connection.alias

    TicketType.objects.using(database).filter(ticket_class="CLASSIC").update(ticket_class="STANDARD")
    TicketType.objects.using(database).filter(ticket_class="VIP").update(ticket_class="PREMIUM")
    TicketType.objects.using(database).filter(
        ticket_class="STANDARD",
        label__in=["Billet classique", "Pass Classique"],
    ).update(label="Pack Standard")
    TicketType.objects.using(database).filter(
        ticket_class="PREMIUM",
        label__in=["Billet VIP", "Pass VIP"],
    ).update(label="Pack Premium")

    for competition in Competition.objects.using(database).filter(is_current=True):
        TicketType.objects.using(database).get_or_create(
            competition_id=competition.pk,
            ticket_class="BASIC",
            defaults={
                "label": "Pack Basic",
                "price_xaf": 1000,
                "is_active": True,
            },
        )


def restore_legacy_packages(apps, schema_editor):
    TicketType = apps.get_model("ticketing", "TicketType")
    TicketOrder = apps.get_model("ticketing", "TicketOrder")
    database = schema_editor.connection.alias

    if TicketOrder.objects.using(database).filter(ticket_type__ticket_class="BASIC").exists():
        raise RuntimeError("Basic tickets have been sold; the ticket package migration cannot be reversed.")

    TicketType.objects.using(database).filter(ticket_class="BASIC").delete()
    TicketType.objects.using(database).filter(ticket_class="STANDARD").update(ticket_class="CLASSIC")
    TicketType.objects.using(database).filter(ticket_class="PREMIUM").update(ticket_class="VIP")
    TicketType.objects.using(database).filter(
        ticket_class="CLASSIC",
        label="Pack Standard",
    ).update(label="Billet classique")
    TicketType.objects.using(database).filter(
        ticket_class="VIP",
        label="Pack Premium",
    ).update(label="Billet VIP")


class Migration(migrations.Migration):
    dependencies = [
        ("ticketing", "0002_ticketorder_ticket_code"),
    ]

    operations = [
        migrations.RunPython(rename_packages_and_create_basic, restore_legacy_packages),
        migrations.AlterField(
            model_name="tickettype",
            name="ticket_class",
            field=models.CharField(
                choices=[
                    ("BASIC", "Basic"),
                    ("STANDARD", "Standard"),
                    ("PREMIUM", "Premium"),
                ],
                max_length=12,
            ),
        ),
    ]
