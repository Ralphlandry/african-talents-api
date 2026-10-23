from django.db import migrations


def rename_package_labels(apps, schema_editor):
    TicketType = apps.get_model("ticketing", "TicketType")
    database = schema_editor.connection.alias
    for ticket_class, previous_labels, new_label in [
        ("BASIC", ["Pack Basic"], "Pass Basic"),
        ("STANDARD", ["Pack Standard"], "Pass Standard"),
        ("PREMIUM", ["Pack Premium"], "Pass Premium"),
    ]:
        TicketType.objects.using(database).filter(
            ticket_class=ticket_class,
            label__in=previous_labels,
        ).update(label=new_label)


def restore_package_labels(apps, schema_editor):
    TicketType = apps.get_model("ticketing", "TicketType")
    database = schema_editor.connection.alias
    for ticket_class, pass_label, pack_label in [
        ("BASIC", "Pass Basic", "Pack Basic"),
        ("STANDARD", "Pass Standard", "Pack Standard"),
        ("PREMIUM", "Pass Premium", "Pack Premium"),
    ]:
        TicketType.objects.using(database).filter(
            ticket_class=ticket_class,
            label=pass_label,
        ).update(label=pack_label)


class Migration(migrations.Migration):
    dependencies = [
        ("ticketing", "0003_ticket_type_packages"),
    ]

    operations = [
        migrations.RunPython(rename_package_labels, restore_package_labels),
    ]
