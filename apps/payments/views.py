import logging

from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.core.exceptions import DomainError
from apps.core.permissions import RBACPermission

from . import services
from .models import Payment
from .serializers import PaymentSerializer

logger = logging.getLogger(__name__)


class WebhookRateThrottle(AnonRateThrottle):
    scope = "webhook"


@extend_schema(tags=["payments"])
class HRSkillsWebhookView(APIView):
    """
    POST /api/v1/payments/webhooks/hrskills/ — appelé par HR-Skills Pay, jamais par le frontend.
    Ni authentification JWT ni CSRF : la sécurité vient uniquement de la signature HMAC du corps.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [WebhookRateThrottle]

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        raw_body = request.body  # lu AVANT tout accès à request.data, pour garantir le corps brut non modifié
        signature = request.headers.get("X-Hub-Signature", "")
        try:
            services.handle_webhook(raw_body, signature, request=request)
        except DomainError:
            raise
        except Exception:
            logger.exception("Erreur inattendue dans le traitement du webhook HR-Skills Pay")
            # On répond quand même 200 : une erreur de notre côté ne doit pas déclencher
            # une tempête de re-livraisons du webhook. L'erreur est journalisée pour investigation.
        return Response({"success": True}, status=200)


@extend_schema(tags=["payments"])
class PaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Payment.objects.select_related(
        "vote_order", "vote_order__candidate", "ticket_order", "ticket_order__ticket_type"
    )
    serializer_class = PaymentSerializer
    permission_classes = [RBACPermission]
    permission_map = {"list": "payments.view", "retrieve": "payments.view", "refund": "payments.refund"}
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "operator", "environment"]
    search_fields = ["reference", "provider_reference"]
    ordering = ["-initiated_at"]

    @action(detail=True, methods=["post"])
    def refund(self, request, pk=None):
        payment = services.refund_payment(request.user, self.get_object(), request=request)
        return Response(self.get_serializer(payment).data)
