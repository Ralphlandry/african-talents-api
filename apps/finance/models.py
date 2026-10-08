from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class ReconciliationRun(BaseModel):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STATUS_CHOICES = [(RUNNING, "En cours"), (COMPLETED, "Terminé"), (FAILED, "Échoué")]

    period_from = models.DateField()
    period_to = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=RUNNING)
    started_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Rapprochement {self.period_from} → {self.period_to} ({self.status})"


class ReconciliationItem(BaseModel):
    MATCH = "MATCH"
    MISSING = "MISSING"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    STATUS_MISMATCH = "STATUS_MISMATCH"
    UNMATCHED_PROVIDER = "UNMATCHED_PROVIDER"  # argent vu chez HR-Skills Pay sans paiement interne correspondant
    RESULT_CHOICES = [
        (MATCH, "MATCH"), (MISSING, "MISSING"), (AMOUNT_MISMATCH, "AMOUNT MISMATCH"),
        (STATUS_MISMATCH, "STATUS MISMATCH"), (UNMATCHED_PROVIDER, "UNMATCHED PROVIDER"),
    ]

    run = models.ForeignKey(ReconciliationRun, on_delete=models.CASCADE, related_name="items")
    internal_reference = models.CharField(max_length=32, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True)
    expected_xaf = models.IntegerField(null=True, blank=True)
    received_xaf = models.IntegerField(null=True, blank=True)
    internal_status = models.CharField(max_length=16, blank=True)
    provider_status = models.CharField(max_length=32, blank=True)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, db_index=True)

    class Meta:
        ordering = ["result", "internal_reference"]

    def __str__(self):
        return f"{self.internal_reference or self.provider_reference} — {self.result}"
