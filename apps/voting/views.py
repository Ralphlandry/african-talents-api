from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, viewsets
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import RBACPermission

from . import services
from .filters import VoteFilter
from .models import Vote, VotePackage
from .serializers import VoteAdjustSerializer, VotePackageSerializer, VoteRecordSerializer


@extend_schema(tags=["vote-packages"])
class VotePackageViewSet(viewsets.ModelViewSet):
    """Forfaits de vote définis par l'admin (quantité + prix) — décision B, aucun prix codé en dur."""

    queryset = VotePackage.objects.select_related("competition")
    serializer_class = VotePackageSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "vote_packages.view", "retrieve": "vote_packages.view",
        "create": "vote_packages.create", "update": "vote_packages.edit", "partial_update": "vote_packages.edit",
        "destroy": "vote_packages.delete",
    }
    filterset_fields = ["competition", "is_active"]
    ordering = ["order"]
    pagination_class = None

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package = services.create_package(request.user, request=request, **serializer.validated_data)
        return Response(self.get_serializer(package).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        package = services.update_package(request.user, instance, request=request, **serializer.validated_data)
        return Response(self.get_serializer(package).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_package(request.user, self.get_object(), request=request)
        return Response(status=204)


@extend_schema(tags=["votes"])
class VoteListView(viewsets.ReadOnlyModelViewSet):
    """Journal des votes (le grand livre lui-même) — filtrable, jamais modifiable ici."""

    queryset = Vote.objects.select_related("candidate", "phase")
    serializer_class = VoteRecordSerializer
    permission_classes = [RBACPermission]
    permission_map = {"list": "votes.view", "retrieve": "votes.view"}
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class = VoteFilter
    ordering = ["-created_at"]

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST")  # passer par /votes/adjust/, jamais d'écriture directe sur le ledger


class VoteAdjustView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"POST": "votes.adjust"}

    @extend_schema(tags=["votes"], request=VoteAdjustSerializer, responses={201: VoteRecordSerializer})
    def post(self, request):
        serializer = VoteAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vote = services.adjust_votes(request.user, request=request, **serializer.validated_data)
        return Response(VoteRecordSerializer(vote).data, status=201)


def _current_competition():
    from apps.competition.models import Competition

    return Competition.objects.filter(is_current=True).first()


class VotesByCategoryView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"GET": "votes.statistics"}

    @extend_schema(tags=["votes"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        competition = _current_competition()
        return Response(services.votes_by_category(competition) if competition else [])


class VotesSeriesView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"GET": "votes.statistics"}

    @extend_schema(
        tags=["votes"],
        parameters=[OpenApiParameter("days", OpenApiTypes.INT, default=14, description="Taille de la fenêtre, en jours.")],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        competition = _current_competition()
        if not competition:
            return Response([])
        days = int(request.query_params.get("days", 14))
        return Response(services.votes_series(competition, days=days))


class RankingView(APIView):
    """Classement admin (avec filtres phase/catégorie). Version publique : apps/publicapi."""

    permission_classes = [RBACPermission]
    permission_map = {"GET": "rankings.view"}

    @extend_schema(
        tags=["rankings"],
        parameters=[
            OpenApiParameter("category", OpenApiTypes.UUID, required=False),
            OpenApiParameter("phase", OpenApiTypes.UUID, required=False),
            OpenApiParameter("cumulative", OpenApiTypes.BOOL, default=True, description="False = uniquement la phase en cours."),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        from apps.categories.models import Category
        from apps.competition.models import Phase

        competition = _current_competition()
        if not competition:
            return Response([])
        category = Category.objects.filter(pk=request.query_params.get("category")).first() if request.query_params.get("category") else None
        phase = Phase.objects.filter(pk=request.query_params.get("phase")).first() if request.query_params.get("phase") else None
        cumulative = request.query_params.get("cumulative", "true").lower() != "false"
        qs = services.ranked_candidates(competition, category=category, phase=phase, cumulative=cumulative)
        data = [
            {"rank": i + 1, "id": str(c.id), "code": c.code, "name": c.display_name, "votes_total": c.votes_total_annotated or 0}
            for i, c in enumerate(qs)
        ]
        return Response(data)
