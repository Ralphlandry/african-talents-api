from rest_framework import serializers

from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetBriefSerializer

from .models import SiteSettings


class StatItemSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=120)
    value = serializers.CharField(max_length=60)


class SiteSettingsSerializer(serializers.ModelSerializer):
    logo = MediaAssetBriefSerializer(read_only=True)
    logo_id = serializers.PrimaryKeyRelatedField(
        source="logo", queryset=MediaAsset.objects.all(), required=False, allow_null=True, write_only=True
    )
    favicon = MediaAssetBriefSerializer(read_only=True)
    favicon_id = serializers.PrimaryKeyRelatedField(
        source="favicon", queryset=MediaAsset.objects.all(), required=False, allow_null=True, write_only=True
    )
    stats = StatItemSerializer(many=True, required=False)

    class Meta:
        model = SiteSettings
        fields = [
            "site_name", "tagline", "description", "logo", "logo_id", "favicon", "favicon_id",
            "facebook_url", "instagram_url", "tiktok_url", "youtube_url",
            "contact_phone", "contact_phone_2", "contact_whatsapp", "contact_email", "contact_address",
            "stats", "updated_at",
        ]
        read_only_fields = ["updated_at"]

