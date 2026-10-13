from rest_framework.routers import SimpleRouter

from .views import PartnerViewSet

router = SimpleRouter()
router.register("partners", PartnerViewSet, basename="partner")
urlpatterns = router.urls
