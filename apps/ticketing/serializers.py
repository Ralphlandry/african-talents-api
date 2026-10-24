from rest_framework import serializers

from apps.candidates.models import Candidate

from .models import TicketOrder, TicketType


class TicketTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketType
        fields = ["id", "competition", "ticket_class", "label", "price_xaf", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_price_xaf(self, value):
        if value < 1:
            raise serializers.ValidationError("Le prix doit être supérieur à 0.")
        return value

    def validate_competition(self, value):
        if not value.is_current:
            raise serializers.ValidationError("Les tarifs ne peuvent être configurés que pour la compétition en cours.")
        return value


class PublicTicketTypeSerializer(serializers.ModelSerializer):
    competition_start_date = serializers.DateField(source="competition.start_date", read_only=True)

    class Meta:
        model = TicketType
        fields = ["id", "ticket_class", "label", "price_xaf", "competition_start_date"]


class TicketOrderCreateSerializer(serializers.Serializer):
    ticket_type = serializers.PrimaryKeyRelatedField(queryset=TicketType.objects.filter(is_active=True))
    first_name = serializers.CharField(max_length=100, trim_whitespace=True)
    last_name = serializers.CharField(max_length=100, trim_whitespace=True)
    phone = serializers.RegexField(r"^\+?[0-9]{9,15}$")
    operator = serializers.ChoiceField(choices=["MTN", "ORANGE"])
    promo_code = serializers.CharField(max_length=32, required=False, allow_blank=True, trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=100)
    accept_terms = serializers.BooleanField()

    def validate_accept_terms(self, value):
        if not value:
            raise serializers.ValidationError("Vous devez accepter les conditions pour acheter un billet.")
        return value

    def validate_promo_code(self, value):
        if not value:
            return ""
        ticket_type = self.initial_data.get("ticket_type")
        candidates = Candidate.objects.filter(
            competition__is_current=True, status=Candidate.PUBLISHED, is_active=True
        )
        candidate = candidates.filter(promo_code__iexact=value).first()
        if candidate is None:
            candidate = candidates.filter(promo_code__isnull=True, code__iexact=value).first()
        if candidate is None:
            raise serializers.ValidationError("Ce code promo ne correspond à aucun candidat actif.")
        ticket_competition_id = TicketType.objects.filter(pk=ticket_type, is_active=True).values_list(
            "competition_id", flat=True
        ).first()
        if str(candidate.competition_id) != str(ticket_competition_id):
            raise serializers.ValidationError("Ce code promo n'appartient pas à la compétition du billet.")
        return value.strip().upper()

    def validate(self, attrs):
        code = attrs.get("promo_code", "")
        ticket_type = attrs["ticket_type"]
        if not ticket_type.competition.is_current:
            raise serializers.ValidationError({"ticket_type": "Ce billet n'est pas disponible pour la compétition en cours."})
        if not ticket_type.competition.ticket_sales_open:
            raise serializers.ValidationError({"ticket_type": "La vente des billets est actuellement fermée."})
        if code:
            candidates = Candidate.objects.filter(
                competition=ticket_type.competition, status=Candidate.PUBLISHED, is_active=True
            )
            candidate = candidates.filter(promo_code__iexact=code).first()
            if candidate is None:
                candidate = candidates.filter(promo_code__isnull=True, code__iexact=code).first()
            if candidate is None:
                raise serializers.ValidationError({"promo_code": "Ce code promo n'appartient pas à la compétition du billet."})
            attrs["promo_candidate"] = candidate
        return attrs


class TicketOrderStatusSerializer(serializers.ModelSerializer):
    ticket_label = serializers.CharField(source="ticket_type.label", read_only=True)
    ticket_class = serializers.CharField(source="ticket_type.ticket_class", read_only=True)
    promo_candidate_name = serializers.SerializerMethodField()
    promo_code = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()

    class Meta:
        model = TicketOrder
        fields = [
            "order_number", "status", "first_name", "last_name", "ticket_label", "ticket_class",
            "amount_xaf", "promo_code", "promo_candidate_name", "created_at", "pdf_url",
        ]

    first_name = serializers.CharField(source="buyer_first_name", read_only=True)
    last_name = serializers.CharField(source="buyer_last_name", read_only=True)

    def get_promo_candidate_name(self, obj):
        return obj.promo_candidate.display_name if obj.promo_candidate_id else None

    def get_promo_code(self, obj):
        if not obj.promo_candidate_id:
            return None
        return obj.promo_candidate.promo_code or obj.promo_candidate.code

    def get_pdf_url(self, obj):
        return (
            f"/public/ticket-orders/{obj.order_number}/pdf/"
            if obj.status == TicketOrder.PAID
            else None
        )
