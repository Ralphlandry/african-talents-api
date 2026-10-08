from rest_framework import serializers

from .models import Competition, Phase


class PhaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Phase
        fields = ["id", "name", "order", "start_date", "end_date", "status"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "La date de fin doit être postérieure à la date de début."})
        return attrs


class CompetitionSerializer(serializers.ModelSerializer):
    phases = PhaseSerializer(many=True, read_only=True)
    current_phase = serializers.SerializerMethodField()

    class Meta:
        model = Competition
        fields = [
            "id", "name", "slug", "description", "start_date", "end_date",
            "status", "votes_open", "is_current", "phases", "current_phase",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "is_current", "phases", "current_phase", "created_at", "updated_at"]

    def get_current_phase(self, obj) -> dict | None:
        phase = next((p for p in obj.phases.all() if p.status == Phase.ACTIVE), None)
        return PhaseSerializer(phase).data if phase else None

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "La date de fin doit être postérieure à la date de début."})
        return attrs


class CompetitionCreateSerializer(CompetitionSerializer):
    class Meta(CompetitionSerializer.Meta):
        pass
