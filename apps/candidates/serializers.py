from django.utils.text import slugify
from rest_framework import serializers

from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetBriefSerializer

from .models import Candidate


class CandidateSerializer(serializers.ModelSerializer):
    photo = MediaAssetBriefSerializer(read_only=True)
    photo_id = serializers.PrimaryKeyRelatedField(
        source="photo", queryset=MediaAsset.objects.all(), required=False, allow_null=True, write_only=True
    )
    gallery = MediaAssetBriefSerializer(many=True, read_only=True)
    gallery_ids = serializers.PrimaryKeyRelatedField(
        source="gallery", queryset=MediaAsset.objects.all(), required=False, many=True, write_only=True
    )
    display_name = serializers.CharField(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)
    votes_total = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            "id", "competition", "category", "category_name", "current_phase", "code",
            "first_name", "last_name", "display_name", "slug", "bio", "city", "country",
            "photo", "photo_id", "gallery", "gallery_ids",
            "facebook_url", "instagram_url", "tiktok_url",
            "status", "is_active", "votes_total", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "votes_total", "created_at", "updated_at"]

    def get_votes_total(self, obj) -> int:
        # Somme réelle branchée au jalon 3 (ledger de votes). 0 tant que le système de vote n'existe pas.
        return getattr(obj, "votes_total_annotated", 0) or 0

    def validate_code(self, value):
        return value.strip().upper()


class CandidateWriteSerializer(CandidateSerializer):
    class Meta(CandidateSerializer.Meta):
        pass

    def create(self, validated_data):
        validated_data.setdefault("slug", slugify(f"{validated_data['first_name']}-{validated_data['last_name']}")[:220])
        gallery = validated_data.pop("gallery", None)
        instance = Candidate.objects.create(**validated_data)
        if gallery is not None:
            instance.gallery.set(gallery)
        return instance


class CandidateBulkActionSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=200)
