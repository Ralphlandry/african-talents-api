from django.db import migrations


def normalize_team_member_order(apps, schema_editor):
    TeamMember = apps.get_model("team", "TeamMember")
    database = schema_editor.connection.alias

    for member_type in (
        TeamMember.objects.using(database).values_list("type", flat=True).distinct()
    ):
        members = (
            TeamMember.objects.using(database)
            .filter(type=member_type)
            .order_by("order", "full_name", "pk")
        )
        for position, member in enumerate(members.iterator(), start=1):
            TeamMember.objects.using(database).filter(pk=member.pk).update(order=position)


class Migration(migrations.Migration):
    dependencies = [
        ("team", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(normalize_team_member_order, migrations.RunPython.noop),
    ]
