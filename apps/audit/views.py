from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from apps.core.permissions import RBACPermission

from .filters import AuditLogFilter
from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditLogSerializer
    permission_classes = [RBACPermission]
    permission_map = {"list": "audit.view", "retrieve": "audit.view"}
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AuditLogFilter
    search_fields = ["actor_email", "actor_name", "action", "resource"]
    ordering_fields = ["created_at", "action", "module"]
    ordering = ["-created_at"]
