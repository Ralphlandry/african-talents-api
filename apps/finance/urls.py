from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    FinanceOverviewView,
    FinanceReportView,
    MerchantAccountView,
    ReconciliationRunTriggerView,
    ReconciliationRunViewSet,
)

router = SimpleRouter()
router.register("finance/reconciliation-runs", ReconciliationRunViewSet, basename="reconciliation-run")

urlpatterns = [
    path("finance/overview/", FinanceOverviewView.as_view(), name="finance-overview"),
    path("finance/merchant-account/", MerchantAccountView.as_view(), name="finance-merchant-account"),
    path("finance/reconciliation/run/", ReconciliationRunTriggerView.as_view(), name="finance-reconciliation-run"),
    path("finance/reports/", FinanceReportView.as_view(), name="finance-reports"),
    *router.urls,
]
