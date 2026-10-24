from rest_framework.routers import SimpleRouter
from django.urls import path

from .views import AdvertisementViewSet, PublicAdvertisementListView

router = SimpleRouter()
router.register("advertisements", AdvertisementViewSet, basename="advertisement")

urlpatterns = [
    *router.urls,
    path("public/advertisements/", PublicAdvertisementListView.as_view(), name="public-advertisements"),
]
