from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import RBACPermission

from . import services
from .models import Competition
from .serializers import CompetitionSerializer, PhaseSerializer


class CompetitionViewSet(viewsets.ModelViewSet):
    queryset = Competition.objects.prefetch_related("phases")
    serializer_class = CompetitionSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "competition.view", "retrieve": "competition.view",
        "create": "competition.edit", "update": "competition.edit", "partial_update": "competition.edit",
        "destroy": "competition.edit", "start": "competition.start", "stop": "competition.stop",
        "toggle_votes": "competition.edit",
        "add_phase": "competition.edit", "update_phase": "competition.edit", "delete_phase": "competition.edit",
    }
    pagination_class = None

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        competition = services.create_competition(request.user, request=request, **serializer.validated_data)
        return Response(self.get_serializer(competition).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        competition = services.update_competition(request.user, instance, request=request, **serializer.validated_data)
        return Response(self.get_serializer(competition).data)

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        competition = services.set_status(request.user, self.get_object(), Competition.ACTIVE, request=request)
        return Response(self.get_serializer(competition).data)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        competition = services.set_status(request.user, self.get_object(), Competition.ENDED, request=request)
        return Response(self.get_serializer(competition).data)

    @action(detail=True, methods=["post"], url_path="toggle-votes")
    def toggle_votes(self, request, pk=None):
        competition = self.get_object()
        competition = services.toggle_votes(request.user, competition, not competition.votes_open, request=request)
        return Response(self.get_serializer(competition).data)

    @action(detail=True, methods=["post"], url_path="phases")
    def add_phase(self, request, pk=None):
        serializer = PhaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phase = services.upsert_phase(request.user, self.get_object(), request=request, **serializer.validated_data)
        return Response(PhaseSerializer(phase).data, status=201)

    @action(detail=True, methods=["patch"], url_path=r"phases/(?P<phase_id>[^/.]+)")
    def update_phase(self, request, pk=None, phase_id=None):
        competition = self.get_object()
        phase = competition.phases.get(pk=phase_id)
        serializer = PhaseSerializer(phase, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        phase = services.upsert_phase(request.user, competition, phase, request=request, **serializer.validated_data)
        return Response(PhaseSerializer(phase).data)

    @update_phase.mapping.delete
    def delete_phase(self, request, pk=None, phase_id=None):
        competition = self.get_object()
        phase = competition.phases.get(pk=phase_id)
        services.delete_phase(request.user, phase, request=request)
        return Response(status=204)
