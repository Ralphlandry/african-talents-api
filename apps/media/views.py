from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, parsers, viewsets
from rest_framework.response import Response

from apps.core.permissions import RBACPermission

from . import services
from .models import MediaAsset
from .serializers import MediaAssetSerializer


class MediaAssetViewSet(viewsets.ModelViewSet):
    queryset = MediaAsset.objects.select_related("uploaded_by")
    serializer_class = MediaAssetSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "media.view", "retrieve": "media.view",
        "create": "media.upload", "destroy": "media.delete",
    }
    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["kind", "usage"]
    search_fields = ["original_name"]
    ordering = ["-created_at"]

    def create(self, request, *args, **kwargs):
        file_obj = request.FILES.get("file")
        if not file_obj:
            from apps.core.exceptions import DomainError

            raise DomainError("Aucun fichier envoyé.", code="FILE_MISSING")
        asset = services.upload_media(request.user, file_obj=file_obj, usage=request.data.get("usage", ""), request=request)
        return Response(MediaAssetSerializer(asset, context={"request": request}).data, status=201)

    def destroy(self, request, *args, **kwargs):
        services.delete_media(request.user, self.get_object(), request=request)
        return Response(status=204)
