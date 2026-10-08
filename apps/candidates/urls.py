from rest_framework.routers import SimpleRouter

from .views import CandidateViewSet

router = SimpleRouter()
router.register("candidates", CandidateViewSet, basename="candidate")
urlpatterns = router.urls
