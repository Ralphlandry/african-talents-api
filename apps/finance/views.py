from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import RBACPermission

from . import services
from .models import ReconciliationRun
from .serializers import (
    FinanceReportRequestSerializer,
    ReconciliationRunRequestSerializer,
    ReconciliationRunSerializer,
)


class FinanceOverviewView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"GET": "payments.statistics"}

    @extend_schema(tags=["finance"], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(services.overview())


class MerchantAccountView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"GET": "merchant.view"}

    @extend_schema(
        tags=["finance"],
        parameters=[OpenApiParameter("refresh", OpenApiTypes.STR, description="'1' pour ignorer le cache de 2 min.")],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        force_refresh = request.query_params.get("refresh") == "1"
        return Response(services.merchant_account(force_refresh=force_refresh))


@extend_schema(tags=["finance"])
class ReconciliationRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ReconciliationRun.objects.prefetch_related("items")
    serializer_class = ReconciliationRunSerializer
    permission_classes = [RBACPermission]
    permission_map = {"list": "reconciliation.view", "retrieve": "reconciliation.view"}

    def create(self, request, *args, **kwargs):
        # Exposé séparément via l'action "run" ci-dessous ; ce viewset reste en lecture seule pour list/retrieve.
        from rest_framework.exceptions import MethodNotAllowed

        raise MethodNotAllowed("POST")


class ReconciliationRunTriggerView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"POST": "reconciliation.run"}

    @extend_schema(tags=["finance"], request=ReconciliationRunRequestSerializer, responses={201: ReconciliationRunSerializer})
    def post(self, request):
        serializer = ReconciliationRunRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        run = services.run_reconciliation(request.user, request=request, **serializer.validated_data)
        return Response(ReconciliationRunSerializer(run).data, status=201)


class FinanceReportView(APIView):
    permission_classes = [RBACPermission]
    permission_map = {"GET": "payments.export"}

    @extend_schema(
        tags=["finance"],
        parameters=[
            OpenApiParameter("range", OpenApiTypes.STR, enum=["today", "week", "month", "custom"], default="month"),
            OpenApiParameter("date_from", OpenApiTypes.DATE, description="Requis si range=custom."),
            OpenApiParameter("date_to", OpenApiTypes.DATE, description="Requis si range=custom."),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        serializer = FinanceReportRequestSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report = services.report(range_key=data["range"], date_from=data.get("date_from"), date_to=data.get("date_to"))
        return Response(report)
