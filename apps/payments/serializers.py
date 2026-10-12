from rest_framework import serializers

from .models import Payment, PaymentEvent
from .utils import mask_phone


class PaymentSerializer(serializers.ModelSerializer):
    candidate_name = serializers.SerializerMethodField()
    candidate_code = serializers.SerializerMethodField()
    order_number = serializers.CharField(source="reference", read_only=True)
    ticket_label = serializers.SerializerMethodField()
    order_type = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id", "reference", "order_number", "provider", "provider_reference", "environment",
            "amount_xaf", "currency", "phone", "operator", "status", "fees_xaf", "net_amount_xaf",
            "failure_reason", "candidate_code", "candidate_name", "ticket_label", "order_type",
            "initiated_at", "confirmed_at",
        ]
        read_only_fields = fields

    def get_phone(self, obj) -> str:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.has_permission_key("payments.view_sensitive"):
            return obj.phone
        return mask_phone(obj.phone)

    def get_candidate_name(self, obj):
        return obj.vote_order.candidate.display_name if obj.vote_order_id else None

    def get_candidate_code(self, obj):
        return obj.vote_order.candidate.code if obj.vote_order_id else None

    def get_ticket_label(self, obj):
        return obj.ticket_order.ticket_type.label if obj.ticket_order_id else None

    def get_order_type(self, obj):
        return "ticket" if obj.ticket_order_id else "vote"


class PaymentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentEvent
        fields = ["id", "reference", "event_type", "signature_valid", "processed", "processing_error", "created_at"]
        read_only_fields = fields
