from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import RBACPermission

from . import services
from .models import NewsPost
from .serializers import NewsBulkActionSerializer, NewsPostSerializer


class NewsPostViewSet(viewsets.ModelViewSet):
    queryset = NewsPost.objects.select_related("main_image", "category", "author")
    serializer_class = NewsPostSerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "news.view", "retrieve": "news.view",
        "create": "news.create", "update": "news.edit", "partial_update": "news.edit",
        "destroy": "news.delete", "publish": "news.publish", "unpublish": "news.publish",
        "bulk_publish": "news.publish", "bulk_delete": "news.delete",
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "category"]
    search_fields = ["title", "excerpt"]
    ordering_fields = ["created_at", "published_at", "title"]
    ordering = ["-created_at"]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        post = services.create_post(request.user, request=request, **serializer.validated_data)
        return Response(self.get_serializer(post).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        post = services.update_post(request.user, instance, request=request, **serializer.validated_data)
        return Response(self.get_serializer(post).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_post(request.user, self.get_object(), request=request)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        post = services.publish_now(request.user, self.get_object(), request=request)
        return Response(self.get_serializer(post).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        post = services.unpublish(request.user, self.get_object(), request=request)
        return Response(self.get_serializer(post).data)

    def _bulk_ids(self, request):
        serializer = NewsBulkActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data["ids"]

    @action(detail=False, methods=["post"], url_path="bulk-publish")
    def bulk_publish(self, request):
        count = services.bulk_publish(request.user, self._bulk_ids(request), request=request)
        return Response({"updated": count})

    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        count = services.bulk_delete(request.user, self._bulk_ids(request), request=request)
        return Response({"deleted": count})
