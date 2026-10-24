from rest_framework import serializers

from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetBriefSerializer

from .models import Advertisement


class AdvertisementSerializer(serializers.ModelSerializer):
    image = MediaAssetBriefSerializer(read_only=True)
    image_id = serializers.PrimaryKeyRelatedField(
        source="image",
        queryset=MediaAsset.objects.filter(kind=MediaAsset.KIND_IMAGE),
        required=False,
        allow_null=True,
        write_only=True,
    )
    display_delay_seconds = serializers.IntegerField(min_value=0, max_value=86400)
    dismissal_cooldown_hours = serializers.IntegerField(min_value=0, max_value=8760)

    class Meta:
        model = Advertisement
        fields = [
            "id", "title", "image", "image_id", "placement",
            "display_delay_seconds", "dismissal_cooldown_hours", "button_label",
            "button_url", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        image = attrs.get("image", getattr(self.instance, "image", None))
        if not image:
            raise serializers.ValidationError({"image_id": "Sélectionnez une image pour la publicité."})

        button_url = attrs.get("button_url", getattr(self.instance, "button_url", ""))
        if not button_url.startswith("/") or button_url.startswith("//"):
            raise serializers.ValidationError({"button_url": "Le lien doit être une adresse interne du site."})
        return attrs


class PublicAdvertisementSerializer(serializers.ModelSerializer):
    image = MediaAssetBriefSerializer(read_only=True)

    class Meta:
        model = Advertisement
        fields = [
            "id", "title", "image", "placement",
            "display_delay_seconds", "dismissal_cooldown_hours",
            "button_label", "button_url",
        ]
