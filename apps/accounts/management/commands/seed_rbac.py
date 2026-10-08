from django.core.management.base import BaseCommand

from apps.accounts.rbac import seed_preset_roles, sync_rbac


class Command(BaseCommand):
    help = "Synchronise le catalogue de permissions et crée les rôles prédéfinis manquants (idempotent)."

    def handle(self, *args, **options):
        sync_rbac()
        created = seed_preset_roles()
        if created:
            self.stdout.write(self.style.SUCCESS(f"Rôles créés : {', '.join(created)}"))
        else:
            self.stdout.write("Aucun nouveau rôle à créer.")
