from rest_framework.routers import SimpleRouter

from .views import TeamMemberViewSet

router = SimpleRouter()
router.register("team", TeamMemberViewSet, basename="team-member")
urlpatterns = router.urls
