from rest_framework import serializers

from .models import Payment, PaymentEvent
from .utils import mask_phone


class PaymentSerializer(serializers.ModelSerializer):
    candidate_name = serializers.CharField(source="vote_order.candidate.display_name", read_only=True)
    candidate_code = serializers.CharField(source="vote_order.candidate.code", read_only=True)
    order_number = serializers.CharField(source="vote_order.order_number", read_only=True)
    phone = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            "id", "reference", "order_number", "provider", "provider_reference", "environment",
            "amount_xaf", "currency", "phone", "operator", "status", "fees_xaf", "net_amount_xaf",
            "failure_reason", "candidate_code", "candidate_name", "initiated_at", "confirmed_at",
        ]
        read_only_fields = fields

    def get_phone(self, obj) -> str:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.has_permission_key("payments.view_sensitive"):
            return obj.phone
        return mask_phone(obj.phone)


class PaymentEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentEvent
        fields = ["id", "reference", "event_type", "signature_valid", "processed", "processing_error", "created_at"]
        read_only_fields = fields
