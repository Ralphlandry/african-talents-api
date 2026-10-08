import uuid

from django.conf import settings
from django.db import models

from .constants import AuditModule, AuditResult


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Le journal d'audit est en ajout seul.")

    def delete(self):
        raise PermissionError("Le journal d'audit est en ajout seul.")


class AuditLog(models.Model):
    """Journal officiel des actions (écrit uniquement par le backend, jamais modifiable)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="audit_logs"
    )
    # Instantané conservé même si le compte est supprimé.
    actor_email = models.CharField(max_length=254, blank=True)
    actor_name = models.CharField(max_length=160, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    module = models.CharField(max_length=32, db_index=True)
    resource = models.CharField(max_length=64, blank=True)
    resource_id = models.CharField(max_length=64, blank=True)
    result = models.CharField(max_length=16, choices=AuditResult.CHOICES, default=AuditResult.SUCCESS, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["actor", "-created_at"]), models.Index(fields=["module", "-created_at"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.action} ({self.result})"

    @property
    def module_label(self):
        return AuditModule.LABELS.get(self.module, self.module)

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Une entrée du journal d'audit ne peut pas être modifiée.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Une entrée du journal d'audit ne peut pas être supprimée.")
