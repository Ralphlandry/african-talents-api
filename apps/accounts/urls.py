from django.urls import path
from rest_framework.routers import SimpleRouter

from .views_admin import AdminUserViewSet, PermissionCatalogView, RoleViewSet

router = SimpleRouter()
router.register("admins", AdminUserViewSet, basename="admin-user")
router.register("roles", RoleViewSet, basename="role")

urlpatterns = [path("permissions/", PermissionCatalogView.as_view(), name="permission-catalog"), *router.urls]
