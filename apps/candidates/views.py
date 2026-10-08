from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import RBACPermission
from apps.voting.services import annotate_votes_total

from . import services
from .filters import CandidateFilter
from .models import Candidate
from .serializers import CandidateBulkActionSerializer, CandidateSerializer, CandidateWriteSerializer


class CandidateViewSet(viewsets.ModelViewSet):
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "candidates.view", "retrieve": "candidates.view",
        "create": "candidates.create", "update": "candidates.edit", "partial_update": "candidates.edit",
        "destroy": "candidates.delete", "publish": "candidates.publish",
        "activate": "candidates.edit", "deactivate": "candidates.edit",
        "bulk_publish": "candidates.publish", "bulk_activate": "candidates.edit",
        "bulk_deactivate": "candidates.edit", "bulk_delete": "candidates.delete",
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = CandidateFilter
    search_fields = ["code", "first_name", "last_name", "city"]
    ordering_fields = ["code", "first_name", "created_at"]
    ordering = ["code"]

    def get_queryset(self):
        qs = Candidate.objects.select_related("category", "competition", "current_phase", "photo").prefetch_related("gallery")
        return annotate_votes_total(qs, cumulative=True)

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return CandidateWriteSerializer
        return CandidateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        candidate = services.create_candidate(request.user, request=request, **serializer.validated_data)
        return Response(CandidateSerializer(candidate, context=self.get_serializer_context()).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        candidate = services.update_candidate(request.user, instance, request=request, **serializer.validated_data)
        return Response(CandidateSerializer(candidate, context=self.get_serializer_context()).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_candidate(request.user, self.get_object(), request=request)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        candidate = services.publish(request.user, self.get_object(), request=request)
        return Response(self.get_serializer(candidate).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        candidate = services.set_active(request.user, self.get_object(), True, request=request)
        return Response(self.get_serializer(candidate).data)

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        candidate = services.set_active(request.user, self.get_object(), False, request=request)
        return Response(self.get_serializer(candidate).data)

    def _bulk_ids(self, request):
        serializer = CandidateBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["ids"]

    @action(detail=False, methods=["post"], url_path="bulk-publish")
    def bulk_publish(self, request):
        count = services.bulk_publish(request.user, self._bulk_ids(request), request=request)
        return Response({"updated": count})

    @action(detail=False, methods=["post"], url_path="bulk-activate")
    def bulk_activate(self, request):
        count = services.bulk_set_active(request.user, self._bulk_ids(request), True, request=request)
        return Response({"updated": count})

    @action(detail=False, methods=["post"], url_path="bulk-deactivate")
    def bulk_deactivate(self, request):
        count = services.bulk_set_active(request.user, self._bulk_ids(request), False, request=request)
        return Response({"updated": count})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        count = services.bulk_delete(request.user, self._bulk_ids(request), request=request)
        return Response({"deleted": count})
