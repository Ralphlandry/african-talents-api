from rest_framework import serializers

from apps.media.models import MediaAsset
from apps.media.serializers import MediaAssetBriefSerializer

from .models import TeamMember


class TeamMemberSerializer(serializers.ModelSerializer):
    photo = MediaAssetBriefSerializer(read_only=True)
    photo_id = serializers.PrimaryKeyRelatedField(
        source="photo", queryset=MediaAsset.objects.all(), required=False, allow_null=True, write_only=True
    )

    class Meta:
        model = TeamMember
        fields = [
            "id", "type", "full_name", "role_title", "bio",
            "photo", "photo_id", "order", "is_visible", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

