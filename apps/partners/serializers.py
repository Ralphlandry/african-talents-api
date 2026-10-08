from rest_framework import serializers

from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetBriefSerializer

from .models import Partner


class PartnerSerializer(serializers.ModelSerializer):
    logo = MediaAssetBriefSerializer(read_only=True)
    logo_id = serializers.PrimaryKeyRelatedField(
        source="logo", queryset=MediaAsset.objects.filter(kind=MediaAsset.KIND_IMAGE),
        required=True, write_only=True,
    )

    class Meta:
        model = Partner
        fields = ["id", "name", "logo", "logo_id", "order", "is_visible", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PartnerWriteSerializer(PartnerSerializer):
    class Meta(PartnerSerializer.Meta):
        pass