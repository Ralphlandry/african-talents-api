from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.response import Response

from apps.core.permissions import RBACPermission

from . import services
from .models import TeamMember
from .serializers import TeamMemberSerializer


class TeamMemberViewSet(viewsets.ModelViewSet):
    queryset = TeamMember.objects.select_related("photo")
    serializer_class = TeamMemberSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "team.view", "retrieve": "team.view",
        "create": "team.create", "update": "team.edit", "partial_update": "team.edit", "destroy": "team.delete",
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["type", "is_visible"]
    search_fields = ["full_name", "role_title"]
    ordering = ["type", "order"]
    pagination_class = None

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = services.create_member(request.user, request=request, **serializer.validated_data)
        return Response(self.get_serializer(member).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        member = services.update_member(request.user, instance, request=request, **serializer.validated_data)
        return Response(self.get_serializer(member).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_member(request.user, self.get_object(), request=request)
        return Response(status=204)
