from rest_framework import serializers

from apps.candidates.models import Candidate
from apps.competition.models import Phase
from .models import Vote, VoteOrder, VotePackage


class VotePackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = VotePackage
        fields = ["id", "competition", "label", "quantity", "price_xaf", "is_active", "order", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("La quantité doit être d'au moins 1 vote.")
        return value

    def validate_price_xaf(self, value):
        if value < 1:
            raise serializers.ValidationError("Le prix doit être supérieur à 0.")
        return value


class PublicVotePackageSerializer(serializers.ModelSerializer):
    class Meta:
        model = VotePackage
        fields = ["id", "label", "quantity", "price_xaf"]


class VoteAdjustSerializer(serializers.Serializer):
    candidate = serializers.PrimaryKeyRelatedField(queryset=Candidate.objects.all())
    phase = serializers.PrimaryKeyRelatedField(queryset=Phase.objects.all(), required=False, allow_null=True)
    delta = serializers.IntegerField()
    reason = serializers.CharField(max_length=255, min_length=5)

    def validate_delta(self, value):
        if value == 0:
            raise serializers.ValidationError("L'ajustement ne peut pas être nul.")
        return value


class VoteOrderCreateSerializer(serializers.Serializer):
    """
    Le client choisit un candidat et un FORFAIT (pas une quantité/un prix libres) : le
    montant vient toujours du VotePackage résolu côté serveur.
    """

    candidate = serializers.SlugRelatedField(
        slug_field="slug", queryset=Candidate.objects.filter(status=Candidate.PUBLISHED, is_active=True)
    )
    vote_package = serializers.PrimaryKeyRelatedField(queryset=VotePackage.objects.filter(is_active=True))
    phone = serializers.RegexField(r"^\+?[0-9]{9,15}$")
    operator = serializers.ChoiceField(choices=["MTN", "ORANGE"])
    idempotency_key = serializers.CharField(max_length=100)
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("Vous devez accepter les conditions pour voter.")
        return value


class VoteOrderStatusSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="candidate.display_name", read_only=True)
    candidate_code = serializers.CharField(source="candidate.code", read_only=True)

    class Meta:
        model = VoteOrder
        fields = [
            "order_number", "status", "quantity", "amount_xaf", "operator",
            "candidate_code", "candidate_name", "created_at",
        ]
        read_only_fields = fields


class VoteRecordSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="candidate.display_name", read_only=True)
    candidate_code = serializers.CharField(source="candidate.code", read_only=True)
    category_id = serializers.UUIDField(source="candidate.category_id", read_only=True)

    class Meta:
        model = Vote
        fields = [
            "id", "candidate", "candidate_code", "candidate_name", "category_id", "phase",
            "quantity", "source", "vote_order", "created_by", "reason", "created_at",
        ]
        read_only_fields = fields
