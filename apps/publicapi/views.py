from django.http import JsonResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.candidates.models import Candidate
from apps.categories.models import Category
from apps.competition.models import Competition
from apps.core.exceptions import ServiceUnavailableError
from apps.core.models import SiteSettings
from apps.core.throttles import VoteOrderRateThrottle
from apps.news.models import NewsPost
from apps.partners.models import Partner
from apps.payments.gateway import card_payments_enabled
from apps.payments.models import Payment
from apps.payments.services import initiate_payment, refresh_pending_payment
from apps.team.models import TeamMember
from apps.voting.models import VoteOrder, VotePackage
from apps.voting.serializers import (
    PublicVotePackageSerializer,
    VoteOrderCreateSerializer,
    VoteOrderStatusSerializer,
)
from apps.voting.services import annotate_votes_total, create_order, rank_of, ranked_candidates

from .serializers import (
    PublicCandidateDetailSerializer,
    PublicCandidateListSerializer,
    PublicCategorySerializer,
    PublicCompetitionSerializer,
    PublicNewsDetailSerializer,
    PublicNewsListSerializer,
    PublicPartnerSerializer,
    PublicSiteSettingsSerializer,
    PublicTeamMemberSerializer,
)


class PublicReadOnlyMixin:
    """Aucune authentification, aucune permission RBAC : ces endpoits sont publics par nature."""

    permission_classes = [AllowAny]
    authentication_classes = []


def _current_competition():
    return Competition.objects.prefetch_related("phases").filter(is_current=True).first()


@extend_schema(tags=["public"])
class CurrentCompetitionView(PublicReadOnlyMixin, APIView):
    @extend_schema(responses=PublicCompetitionSerializer, description="Renvoie `null` si aucune compétition n'est marquée comme en cours.")
    def get(self, request):
        competition = _current_competition()
        if competition is None:
            return JsonResponse(None, safe=False)
        return Response(PublicCompetitionSerializer(competition).data)


@extend_schema(tags=["public"])
class PublicCategoryListView(PublicReadOnlyMixin, ListAPIView):
    serializer_class = PublicCategorySerializer
    pagination_class = None

    def get_queryset(self):
        competition = _current_competition()
        qs = Category.objects.filter(status=Category.PUBLISHED).select_related("image")
        return qs.filter(competition=competition) if competition else qs.none()


@extend_schema(
    tags=["public"],
    parameters=[
        OpenApiParameter("category", OpenApiTypes.STR, required=False, description="Slug de la catégorie."),
        OpenApiParameter("search", OpenApiTypes.STR, required=False, description="Recherche sur le prénom/nom."),
    ],
)
class PublicCandidateListView(PublicReadOnlyMixin, ListAPIView):
    serializer_class = PublicCandidateListSerializer

    def get_queryset(self):
        competition = _current_competition()
        qs = (
            Candidate.objects.filter(status=Candidate.PUBLISHED, is_active=True)
            .select_related("category", "photo")
        )
        qs = qs.filter(competition=competition) if competition else qs.none()
        category_slug = self.request.query_params.get("category")
        if category_slug:
            qs = qs.filter(category__slug=category_slug)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(first_name__icontains=search) | qs.filter(last_name__icontains=search)
        return annotate_votes_total(qs, cumulative=True).order_by("code")


@extend_schema(tags=["public"])
class PublicCandidateDetailView(PublicReadOnlyMixin, RetrieveAPIView):
    serializer_class = PublicCandidateDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        qs = Candidate.objects.filter(status=Candidate.PUBLISHED, is_active=True).select_related(
            "category", "photo"
        ).prefetch_related("gallery")
        return annotate_votes_total(qs, cumulative=True)

    def get_object(self):
        candidate = super().get_object()
        candidate.rank_annotated = rank_of(candidate)
        return candidate


@extend_schema(
    tags=["public"],
    parameters=[
        OpenApiParameter("category", OpenApiTypes.STR, required=False, description="Slug de la catégorie."),
        OpenApiParameter("cumulative", OpenApiTypes.BOOL, default=True),
    ],
    responses=OpenApiTypes.OBJECT,
)
class PublicRankingView(PublicReadOnlyMixin, APIView):
    """Le frontend n'affiche que ce que renvoie l'API : le classement officiel est toujours calculé ici."""

    def get(self, request):
        competition = _current_competition()
        if competition is None:
            return Response([])
        category_slug = request.query_params.get("category")
        category = Category.objects.filter(slug=category_slug).first() if category_slug else None
        cumulative = request.query_params.get("cumulative", "true").lower() != "false"
        qs = ranked_candidates(competition, category=category, cumulative=cumulative)
        data = [
            {"rank": i + 1, "code": c.code, "slug": c.slug, "name": c.display_name, "votes_total": c.votes_total_annotated or 0}
            for i, c in enumerate(qs)
        ]
        return Response(data)


@extend_schema(tags=["public"])
class PublicNewsListView(PublicReadOnlyMixin, ListAPIView):
    serializer_class = PublicNewsListSerializer

    def get_queryset(self):
        return NewsPost.objects.filter(status=NewsPost.PUBLISHED).select_related("main_image", "category", "author")


@extend_schema(tags=["public"])
class PublicNewsDetailView(PublicReadOnlyMixin, RetrieveAPIView):
    serializer_class = PublicNewsDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return NewsPost.objects.filter(status=NewsPost.PUBLISHED).select_related("main_image", "category", "author")


@extend_schema(tags=["public"])
class PublicTeamListView(PublicReadOnlyMixin, ListAPIView):
    serializer_class = PublicTeamMemberSerializer
    pagination_class = None

    def get_queryset(self):
        return TeamMember.objects.filter(is_visible=True).select_related("photo")


@extend_schema(tags=["public"])
class PublicPartnerListView(PublicReadOnlyMixin, ListAPIView):
    serializer_class = PublicPartnerSerializer
    pagination_class = None

    def get_queryset(self):
        return Partner.objects.filter(is_visible=True).select_related("logo")


@extend_schema(tags=["public"])
class PublicSiteSettingsView(PublicReadOnlyMixin, RetrieveAPIView):
    serializer_class = PublicSiteSettingsSerializer

    def get_object(self):
        return SiteSettings.load()


@extend_schema(tags=["public"])
class PublicVotePackageListView(PublicReadOnlyMixin, ListAPIView):
    """Forfaits actifs de la compétition en cours — toujours définis par l'admin, jamais un prix fixe côté frontend."""

    serializer_class = PublicVotePackageSerializer
    pagination_class = None

    def get_queryset(self):
        competition = _current_competition()
        qs = VotePackage.objects.filter(is_active=True)
        return qs.filter(competition=competition) if competition else qs.none()


@extend_schema(tags=["public"])
class PublicPaymentMethodsView(PublicReadOnlyMixin, APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        methods = [
            {"id": "ORANGE", "name": "Orange Money", "icon": "OM"},
            {"id": "MTN", "name": "MTN Mobile Money", "icon": "MTN"},
        ]
        if card_payments_enabled():
            methods.append({"id": "CARD", "name": "Visa / Mastercard", "icon": "VISA · MC"})
        return Response({"methods": methods})


@extend_schema(tags=["public"])
class PublicVoteOrderCreateView(PublicReadOnlyMixin, APIView):
    """
    Crée une commande de vote puis initie Mobile Money ou un checkout carte hébergé. Le montant vient
    TOUJOURS du VotePackage résolu côté serveur (jamais d'un prix envoyé par le client).
    Idempotent : rejouer la même idempotency_key (double-clic réseau) renvoie la même commande.
    """

    throttle_classes = [VoteOrderRateThrottle]

    @extend_schema(request=VoteOrderCreateSerializer, responses={201: VoteOrderStatusSerializer, 200: VoteOrderStatusSerializer})
    def post(self, request):
        serializer = VoteOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data["operator"] == "CARD" and not card_payments_enabled():
            raise ServiceUnavailableError("Le paiement par carte est désactivé.", code="CARD_PAYMENTS_DISABLED")

        order, created = create_order(
            candidate=data["candidate"], vote_package=data["vote_package"], phone=data["phone"],
            operator=data["operator"], idempotency_key=data["idempotency_key"], request=request,
        )
        if created:
            try:
                initiate_payment(order, request=request)
            except ServiceUnavailableError:
                pass  # L'échec d'initiation est déjà reflété par le statut FAILED.
            order.refresh_from_db()
        return Response(VoteOrderStatusSerializer(order).data, status=201 if created else 200)


@extend_schema(tags=["public"])
class PublicVoteOrderStatusView(PublicReadOnlyMixin, RetrieveAPIView):
    """Utilisé par le frontend pour interroger l'état d'une commande (polling) après redirection vers le téléphone."""

    serializer_class = VoteOrderStatusSerializer
    lookup_field = "order_number"

    def get_queryset(self):
        return VoteOrder.objects.select_related("candidate", "payment")

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        if order.status == VoteOrder.PENDING:
            try:
                payment = order.payment
            except Payment.DoesNotExist:
                pass
            else:
                refresh_pending_payment(payment, request=request)
            finally:
                order.refresh_from_db()
        return Response(self.get_serializer(order).data)
