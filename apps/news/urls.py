from rest_framework.routers import SimpleRouter

from .views import NewsPostViewSet

router = SimpleRouter()
router.register("news", NewsPostViewSet, basename="news-post")
urlpatterns = router.urls
