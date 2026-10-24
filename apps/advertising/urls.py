from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import AdvertisementViewSet, PublicAdvertisementListView

router = SimpleRouter()
router.register("advertisements", AdvertisementViewSet, basename="advertisement")

urlpatterns = [
    *router.urls,
    path("public/advertisements/", PublicAdvertisementListView.as_view(), name="public-advertisements"),
]
