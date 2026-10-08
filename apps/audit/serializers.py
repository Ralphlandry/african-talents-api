from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    module_label = serializers.CharField(read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            "id", "created_at", "actor", "actor_name", "actor_email", "action", "module", "module_label",
            "resource", "resource_id", "result", "ip", "user_agent", "metadata",
        ]
        read_only_fields = fields
