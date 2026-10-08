import django_filters

from .models import User


class AdminUserFilter(django_filters.FilterSet):
    role = django_filters.UUIDFilter(field_name="role_id")
    is_active = django_filters.BooleanFilter()

    class Meta:
        model = User
        fields = ["role", "is_active"]
