from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.response import Response

from apps.core.permissions import RBACPermission

from . import services
from .models import Partner
from .serializers import PartnerSerializer


class PartnerViewSet(viewsets.ModelViewSet):
    queryset = Partner.objects.select_related("logo")
    serializer_class = PartnerSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "partners.view", "retrieve": "partners.view",
        "create": "partners.create", "update": "partners.edit", "partial_update": "partners.edit",
        "destroy": "partners.delete",
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_visible"]
    search_fields = ["name"]
    ordering = ["order", "name"]
    pagination_class = None

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        partner = services.create_partner(request.user, request=request, **serializer.validated_data)
        return Response(self.get_serializer(partner).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        partner = services.update_partner(request.user, instance, request=request, **serializer.validated_data)
        return Response(self.get_serializer(partner).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_partner(request.user, self.get_object(), request=request)
        return Response(status=204)