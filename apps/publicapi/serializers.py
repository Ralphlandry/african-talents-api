"""
Sérialiseurs de l'API publique : uniquement les champs destinés au site public,
jamais de champ administratif (audit, IDs de création, statuts internes bruts...).
"""
from rest_framework import serializers

from apps.candidates.models import Candidate
from apps.categories.models import Category
from apps.competition.models import Competition, Phase
from apps.core.models import SiteSettings
from apps.media.serializers import MediaAssetBriefSerializer
from apps.news.models import NewsPost
from apps.partners.models import Partner
from apps.team.models import TeamMember


class PublicPhaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Phase
        fields = ["id", "name", "order", "start_date", "end_date", "status"]


class PublicCompetitionSerializer(serializers.ModelSerializer):
    phases = PublicPhaseSerializer(many=True, read_only=True)
    current_phase = serializers.SerializerMethodField()

    class Meta:
        model = Competition
        fields = [
            "id", "name", "slug", "description", "start_date", "end_date",
            "status", "votes_open", "ticket_sales_open", "phases", "current_phase",
        ]

    def get_current_phase(self, obj) -> dict | None:
        phase = next((p for p in obj.phases.all() if p.status == Phase.ACTIVE), None)
        return PublicPhaseSerializer(phase).data if phase else None


class PublicCategorySerializer(serializers.ModelSerializer):
    image = MediaAssetBriefSerializer(read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "icon", "image", "order"]


class PublicCandidateListSerializer(serializers.ModelSerializer):
    photo = MediaAssetBriefSerializer(read_only=True)
    display_name = serializers.CharField(read_only=True)
    category = PublicCategorySerializer(read_only=True)
    votes_total = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            "id", "code", "promo_code", "slug", "display_name", "city", "country",
            "photo", "category", "votes_total",
        ]

    def get_votes_total(self, obj) -> int:
        # Agrégation réelle branchée au jalon 3 (ledger de votes).
        return getattr(obj, "votes_total_annotated", 0) or 0


class PublicCandidateDetailSerializer(PublicCandidateListSerializer):
    gallery = MediaAssetBriefSerializer(many=True, read_only=True)
    rank = serializers.SerializerMethodField()

    class Meta(PublicCandidateListSerializer.Meta):
        fields = PublicCandidateListSerializer.Meta.fields + [
            "bio", "gallery", "facebook_url", "instagram_url", "tiktok_url", "rank",
        ]

    def get_rank(self, obj) -> int | None:
        # Calculé côté service (classement réel), pas ici — cf. apps/publicapi/views.py.
        return getattr(obj, "rank_annotated", None)


class PublicNewsListSerializer(serializers.ModelSerializer):
    main_image = MediaAssetBriefSerializer(read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    author_name = serializers.CharField(source="author.full_name", read_only=True, default="")

    class Meta:
        model = NewsPost
        fields = ["id", "title", "slug", "excerpt", "main_image", "category_name", "author_name", "published_at"]


class PublicNewsDetailSerializer(PublicNewsListSerializer):
    class Meta(PublicNewsListSerializer.Meta):
        fields = PublicNewsListSerializer.Meta.fields + ["content_html"]


class PublicTeamMemberSerializer(serializers.ModelSerializer):
    photo = MediaAssetBriefSerializer(read_only=True)

    class Meta:
        model = TeamMember
        fields = ["id", "type", "full_name", "role_title", "bio", "photo", "order"]


class PublicPartnerSerializer(serializers.ModelSerializer):
    logo = MediaAssetBriefSerializer(read_only=True)

    class Meta:
        model = Partner
        fields = ["id", "name", "logo", "order"]


class PublicSiteSettingsSerializer(serializers.ModelSerializer):
    logo = MediaAssetBriefSerializer(read_only=True)
    favicon = MediaAssetBriefSerializer(read_only=True)

    class Meta:
        model = SiteSettings
        fields = [
            "site_name", "tagline", "description", "logo", "favicon",
            "facebook_url", "instagram_url", "tiktok_url", "youtube_url",
            "contact_phone", "contact_phone_2", "contact_whatsapp", "contact_email", "contact_address",
            "stats",
        ]
