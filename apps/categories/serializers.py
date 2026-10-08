from rest_framework import serializers

from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetBriefSerializer

from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    image = MediaAssetBriefSerializer(read_only=True)
    image_id = serializers.PrimaryKeyRelatedField(
        source="image", queryset=MediaAsset.objects.all(), required=False, allow_null=True, write_only=True
    )

    class Meta:
        model = Category
        fields = [
            "id", "competition", "name", "slug", "description", "icon",
            "image", "image_id", "order", "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "order", "created_at", "updated_at"]

class CategoryReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False)
