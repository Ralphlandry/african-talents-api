from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Permission, Role, User


class RoleBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = ["id", "name", "slug", "is_super_admin"]
        read_only_fields = fields


class MeSerializer(serializers.ModelSerializer):
    role = RoleBriefSerializer(read_only=True)
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "permissions", "is_active", "must_change_password", "last_login"]
        read_only_fields = fields

    def get_permissions(self, obj) -> list:
        return sorted(obj.get_permission_keys())


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": ["Mot de passe actuel incorrect."]})
        if attrs["old_password"] == attrs["new_password"]:
            raise serializers.ValidationError({"new_password": ["Le nouveau mot de passe doit être différent de l'ancien."]})
        try:
            validate_password(attrs["new_password"], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"new_password": list(exc.messages)})
        return attrs


# --------------------------------------------------------------------------
# Administrateurs
# --------------------------------------------------------------------------
class AdminUserSerializer(serializers.ModelSerializer):
    role = RoleBriefSerializer(read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "role", "is_active", "status",
            "must_change_password", "last_login", "created_at",
        ]
        read_only_fields = fields

    def get_status(self, obj) -> str:
        return "active" if obj.is_active else "inactive"


class AdminUserCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=160)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all())
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, trim_whitespace=False)
    is_active = serializers.BooleanField(required=False, default=True)

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Un compte existe déjà avec cet e-mail.")
        return value


class AdminUserUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=160, required=False)
    role = serializers.PrimaryKeyRelatedField(queryset=Role.objects.all(), required=False)
    is_active = serializers.BooleanField(required=False)


# --------------------------------------------------------------------------
# Rôles
# --------------------------------------------------------------------------
class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SlugRelatedField(
        many=True, slug_field="codename", queryset=Permission.objects.all(), required=False
    )
    users_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id", "name", "slug", "description", "color", "is_system", "is_super_admin",
            "permissions", "users_count", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "is_system", "is_super_admin", "users_count", "created_at", "updated_at"]

    def get_users_count(self, obj) -> int:
        annotated = getattr(obj, "users_total", None)
        return annotated if annotated is not None else obj.users.count()
