from rest_framework.routers import SimpleRouter

from .views import CompetitionViewSet

router = SimpleRouter()
router.register("competitions", CompetitionViewSet, basename="competition")
urlpatterns = router.urls
