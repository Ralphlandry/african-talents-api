from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    PublicTicketOrderCreateView,
    PublicTicketOrderStatusView,
    PublicTicketPdfView,
    PublicTicketTypeListView,
    TicketSalesControlView,
    TicketStatisticsView,
    TicketTypeViewSet,
)

router = SimpleRouter()
router.register("ticket-types", TicketTypeViewSet, basename="ticket-type")

urlpatterns = [
    path("", include(router.urls)),
    path("ticket-sales/control/", TicketSalesControlView.as_view(), name="ticket-sales-control"),
    path("ticket-sales/statistics/", TicketStatisticsView.as_view(), name="ticket-statistics"),
    path("public/ticket-types/", PublicTicketTypeListView.as_view(), name="public-ticket-types"),
    path("public/ticket-orders/", PublicTicketOrderCreateView.as_view(), name="public-ticket-order-create"),
    path("public/ticket-orders/<str:order_number>/", PublicTicketOrderStatusView.as_view(), name="public-ticket-order-status"),
    path("public/ticket-orders/<str:order_number>/pdf/", PublicTicketPdfView.as_view(), name="public-ticket-pdf"),
]
