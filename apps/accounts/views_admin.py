from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import RBACPermission

from . import services
from .catalog import GROUP_ORDER
from .filters import AdminUserFilter
from .models import Permission, Role, User
from .serializers import (
    AdminUserCreateSerializer,
    AdminUserSerializer,
    AdminUserUpdateSerializer,
    RoleSerializer,
)


class AdminUserViewSet(viewsets.ModelViewSet):
    """Gestion des administrateurs (réservée aux détenteurs de `admins.*`, normalement le Super Admin)."""

    queryset = User.objects.select_related("role").all()
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "admins.view",
        "retrieve": "admins.view",
        "create": "admins.create",
        "update": "admins.edit",
        "partial_update": "admins.edit",
        "reset_password": "admins.edit",
        "destroy": "admins.delete",
        "activate": "admins.delete",
        "deactivate": "admins.delete",
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AdminUserFilter
    search_fields = ["email", "full_name"]
    ordering_fields = ["full_name", "email", "created_at", "last_login"]
    ordering = ["full_name"]

    def get_serializer_class(self):
        if self.action == "create":
            return AdminUserCreateSerializer
        if self.action in ("update", "partial_update"):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    @extend_schema(request=AdminUserCreateSerializer, responses={201: AdminUserSerializer})
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user, temporary = services.create_admin(
            request.user, email=data["email"], full_name=data["full_name"], role=data["role"],
            password=data.get("password") or None, is_active=data.get("is_active", True), request=request,
        )
        body = AdminUserSerializer(user).data
        if temporary:  # affiché une seule fois, jamais stocké en clair
            body["temporary_password"] = temporary
        return Response(body, status=status.HTTP_201_CREATED)

    @extend_schema(request=AdminUserUpdateSerializer, responses=AdminUserSerializer)
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        target = self.get_object()
        serializer = self.get_serializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        user = services.update_admin(request.user, target, request=request, **serializer.validated_data)
        return Response(AdminUserSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_admin(request.user, self.get_object(), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=None, responses=AdminUserSerializer)
    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = services.set_active(request.user, self.get_object(), True, request=request)
        return Response(AdminUserSerializer(user).data)

    @extend_schema(request=None, responses=AdminUserSerializer)
    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = services.set_active(request.user, self.get_object(), False, request=request)
        return Response(AdminUserSerializer(user).data)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        temporary = services.reset_password(request.user, self.get_object(), request=request)
        return Response({"temporary_password": temporary, "must_change_password": True})


class RoleViewSet(viewsets.ModelViewSet):
    permission_classes = [RBACPermission]
    permission_map = {
        "list": ("admins.view", "admins.permissions"),
        "retrieve": ("admins.view", "admins.permissions"),
        "create": "admins.permissions",
        "update": "admins.permissions",
        "partial_update": "admins.permissions",
        "destroy": "admins.permissions",
    }
    serializer_class = RoleSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name", "slug"]
    ordering = ["name"]
    pagination_class = None  # liste courte, utilisée par les formulaires

    def get_queryset(self):
        from django.db.models import Count

        return Role.objects.prefetch_related("permissions").annotate(users_total=Count("users"))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        role = services.create_role(
            request.user, name=data["name"], description=data.get("description", ""),
            color=data.get("color", "blue"), permissions=data.get("permissions", []), request=request,
        )
        return Response(RoleSerializer(role).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        role = self.get_object()
        serializer = self.get_serializer(role, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        role = services.update_role(
            request.user, role, name=data.get("name"), description=data.get("description"),
            color=data.get("color"), permissions=data.get("permissions"), request=request,
        )
        return Response(RoleSerializer(role).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_role(request.user, self.get_object(), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionCatalogView(APIView):
    """Catalogue de permissions groupé, pour construire la matrice de l'écran « Rôles & permissions »."""

    permission_classes = [RBACPermission]
    permission_map = {"GET": ("admins.view", "admins.permissions")}

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        groups = {}
        for perm in Permission.objects.all():
            group = groups.setdefault(perm.group, {"key": perm.group, "label": perm.group_label, "permissions": []})
            group["permissions"].append({"codename": perm.codename, "label": perm.label})
        ordered = sorted(groups.values(), key=lambda g: GROUP_ORDER.index(g["key"]) if g["key"] in GROUP_ORDER else 999)
        return Response(ordered)
