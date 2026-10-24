from rest_framework import viewsets
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny

from apps.core.permissions import RBACPermission

from .models import Advertisement
from .serializers import AdvertisementSerializer, PublicAdvertisementSerializer


class AdvertisementViewSet(viewsets.ModelViewSet):
    queryset = Advertisement.objects.select_related("image")
    serializer_class = AdvertisementSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": ("advertising.view", "advertising.manage"),
        "retrieve": ("advertising.view", "advertising.manage"),
        "create": "advertising.manage",
        "update": "advertising.manage",
        "partial_update": "advertising.manage",
        "destroy": "advertising.manage",
    }
    pagination_class = None


class PublicAdvertisementListView(ListAPIView):
    serializer_class = PublicAdvertisementSerializer
    permission_classes = [AllowAny]
    authentication_classes = []
    pagination_class = None

    def get_queryset(self):
        return Advertisement.objects.filter(is_active=True).select_related("image")
