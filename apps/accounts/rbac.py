from .catalog import PERMISSION_GROUPS, PRESET_ROLES, SUPER_ADMIN_SLUG


def sync_rbac():
    """Synchronise le catalogue de permissions et garantit l'existence du rôle Super Admin (idempotent)."""
    from .models import Permission

    for group in PERMISSION_GROUPS:
        for codename, label in group["permissions"]:
            Permission.objects.update_or_create(
                codename=codename,
                defaults={"label": label, "group": group["key"], "group_label": group["label"]},
            )
    get_super_admin_role()


def get_super_admin_role():
    from .models import Role

    role, _ = Role.objects.get_or_create(
        slug=SUPER_ADMIN_SLUG,
        defaults={
            "name": "Super Administrateur",
            "description": "Accès complet à la plateforme, y compris la gestion des autres administrateurs.",
            "is_system": True,
            "is_super_admin": True,
            "color": "gold",
        },
    )
    return role


def seed_preset_roles():
    """Crée les rôles prédéfinis manquants (ne touche jamais aux rôles déjà existants/modifiés)."""
    from .models import Permission, Role

    created = []
    for preset in PRESET_ROLES:
        role, was_created = Role.objects.get_or_create(
            slug=preset["slug"],
            defaults={"name": preset["name"], "description": preset["description"], "color": preset["color"]},
        )
        if was_created:
            role.permissions.set(Permission.objects.filter(codename__in=preset["permissions"]))
            created.append(role.slug)
    return created
