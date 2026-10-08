from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.permissions import RBACPermission

from . import services
from .models import Category
from .serializers import CategoryReorderSerializer, CategorySerializer


class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.select_related("image", "competition")
    serializer_class = CategorySerializer
    permission_classes = [RBACPermission]
    permission_map = {
        "list": "categories.view", "retrieve": "categories.view",
        "create": "categories.create", "update": "categories.edit", "partial_update": "categories.edit",
        "destroy": "categories.delete", "publish": "categories.publish", "unpublish": "categories.publish",
        "reorder": "categories.edit",
    }
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["competition", "status"]
    search_fields = ["name"]
    ordering = ["order"]
    pagination_class = None

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        category = services.create_category(request.user, request=request, **serializer.validated_data)
        return Response(self.get_serializer(category).data, status=201)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        category = services.update_category(request.user, instance, request=request, **serializer.validated_data)
        return Response(self.get_serializer(category).data)

    def destroy(self, request, *args, **kwargs):
        services.delete_category(request.user, self.get_object(), request=request)
        return Response(status=204)

    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        category = services.set_status(request.user, self.get_object(), Category.PUBLISHED, request=request)
        return Response(self.get_serializer(category).data)

    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        category = services.set_status(request.user, self.get_object(), Category.DRAFT, request=request)
        return Response(self.get_serializer(category).data)

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        serializer = CategoryReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reorder(request.user, serializer.validated_data["ordered_ids"], request=request)
        return Response(self.get_serializer(self.get_queryset(), many=True).data)
