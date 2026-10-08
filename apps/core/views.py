from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.constants import AuditAction, AuditModule
from apps.audit.services import record

from .models import SiteSettings
from .permissions import RBACPermission
from .serializers import SiteSettingsSerializer


class HealthView(APIView):
    """État de santé (base de données + cache). Utilisé par le healthcheck Docker."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(responses=OpenApiTypes.OBJECT, auth=[])
    def get(self, request):
        try:
            connection.ensure_connection()
            cache.set("health-check", "ok", 5)
            cache_ok = cache.get("health-check") == "ok"
        except Exception:
            return Response({"status": "unavailable"}, status=503)
        return Response({"status": "ok" if cache_ok else "degraded"}, status=200 if cache_ok else 503)


class SiteSettingsView(RetrieveUpdateAPIView):
    """Paramètres généraux du site (singleton). Le prix des votes n'est pas ici : voir VotePackage (jalon 3)."""

    serializer_class = SiteSettingsSerializer
    permission_classes = [RBACPermission]
    permission_map = {"GET": "settings.view", "PUT": "settings.edit", "PATCH": "settings.edit"}

    def get_object(self):
        return SiteSettings.load()

    def perform_update(self, serializer):
        instance = serializer.save()
        record(request=self.request, actor=self.request.user, action=AuditAction.SETTINGS_UPDATED,
               module=AuditModule.SETTINGS, resource="site_settings", metadata={"fields": list(self.request.data.keys())})
        return instance


def _json_error(status, code, message):
    return JsonResponse({"success": False, "message": message, "code": code}, status=status)


def handler404(request, exception=None):
    return _json_error(404, "NOT_FOUND", "Ressource introuvable.")


def handler500(request):
    return _json_error(500, "INTERNAL_ERROR", "Une erreur interne est survenue.")
