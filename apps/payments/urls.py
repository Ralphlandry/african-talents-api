from rest_framework.routers import SimpleRouter

from django.urls import path

from .views import HRSkillsWebhookView, PaymentViewSet

router = SimpleRouter()
router.register("payments", PaymentViewSet, basename="payment")

urlpatterns = [
    path("payments/webhooks/hrskills/", HRSkillsWebhookView.as_view(), name="hrskills-webhook"),
    *router.urls,
]
