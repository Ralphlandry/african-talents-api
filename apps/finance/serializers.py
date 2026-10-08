from rest_framework import serializers

from .models import ReconciliationItem, ReconciliationRun


class ReconciliationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReconciliationItem
        fields = [
            "id", "internal_reference", "provider_reference", "expected_xaf", "received_xaf",
            "internal_status", "provider_status", "result",
        ]
        read_only_fields = fields


class ReconciliationRunSerializer(serializers.ModelSerializer):
    items = ReconciliationItemSerializer(many=True, read_only=True)
    anomalies_count = serializers.SerializerMethodField()

    class Meta:
        model = ReconciliationRun
        fields = ["id", "period_from", "period_to", "status", "finished_at", "error_message", "items", "anomalies_count", "created_at"]
        read_only_fields = fields

    def get_anomalies_count(self, obj) -> int:
        return sum(1 for item in obj.items.all() if item.result != ReconciliationItem.MATCH)


class ReconciliationRunRequestSerializer(serializers.Serializer):
    period_from = serializers.DateField()
    period_to = serializers.DateField()

    def validate(self, attrs):
        if attrs["period_to"] < attrs["period_from"]:
            raise serializers.ValidationError("La date de fin doit être postérieure à la date de début.")
        return attrs


class FinanceReportRequestSerializer(serializers.Serializer):
    range = serializers.ChoiceField(choices=["today", "week", "month", "custom"], default="month")
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)

    def validate(self, attrs):
        if attrs.get("range") == "custom" and not (attrs.get("date_from") and attrs.get("date_to")):
            raise serializers.ValidationError("date_from et date_to sont requis pour une période personnalisée.")
        return attrs
