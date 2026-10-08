from rest_framework import serializers

from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetBriefSerializer

from .models import NewsPost


class NewsPostSerializer(serializers.ModelSerializer):
    main_image = MediaAssetBriefSerializer(read_only=True)
    main_image_id = serializers.PrimaryKeyRelatedField(
        source="main_image", queryset=MediaAsset.objects.all(), required=False, allow_null=True, write_only=True
    )
    author_name = serializers.CharField(source="author.full_name", read_only=True, default="")
    category_name = serializers.CharField(source="category.name", read_only=True, default="")

    class Meta:
        model = NewsPost
        fields = [
            "id", "title", "slug", "excerpt", "content_html", "main_image", "main_image_id",
            "category", "category_name", "author", "author_name", "status",
            "scheduled_at", "published_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "author", "published_at", "created_at", "updated_at"]

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", NewsPost.DRAFT))
        scheduled_at = attrs.get("scheduled_at", getattr(self.instance, "scheduled_at", None))
        if status == NewsPost.SCHEDULED and not scheduled_at:
            raise serializers.ValidationError({"scheduled_at": "Une date de programmation est requise."})
        return attrs


class NewsBulkActionSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=200)
