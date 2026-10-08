from django.contrib import admin

from .models import Permission, Role, User


class ReadOnlyAdmin(admin.ModelAdmin):
    """Consultation seule : les comptes et rôles se gèrent via l'API/l'espace admin (mots de passe, audit)."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(User)
class UserAdmin(ReadOnlyAdmin):
    list_display = ("email", "full_name", "role", "is_active", "last_login")
    search_fields = ("email", "full_name")
    exclude = ("password",)


@admin.register(Role)
class RoleAdmin(ReadOnlyAdmin):
    list_display = ("name", "slug", "is_system", "is_super_admin")


@admin.register(Permission)
class PermissionAdmin(ReadOnlyAdmin):
    list_display = ("codename", "label", "group")
