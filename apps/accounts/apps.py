from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _sync_after_migrate(sender, **kwargs):
    from .rbac import sync_rbac

    sync_rbac()


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        # Le catalogue de permissions et le rôle Super Admin sont resynchronisés à chaque migrate.
        post_migrate.connect(_sync_after_migrate, sender=self)
