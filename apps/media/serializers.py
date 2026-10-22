from rest_framework import serializers

from .models import MediaAsset


class MediaAssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()
    size_kb = serializers.IntegerField(read_only=True)

    class Meta:
        model = MediaAsset
        fields = ["id", "url", "original_name", "kind", "mime_type", "size_kb", "usage", "created_at"]
        read_only_fields = fields

    def get_url(self, obj) -> str:
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url


class MediaAssetBriefSerializer(serializers.ModelSerializer):
    """Utilisé en lecture imbriquée (photo d'un candidat, image d'un article...)."""

    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ["id", "url", "original_name"]
        read_only_fields = fields

    def get_url(self, obj) -> str:
        if obj is None:
            return None
        request = self.context.get("request")
        url = obj.file.url
        return request.build_absolute_uri(url) if request else url
