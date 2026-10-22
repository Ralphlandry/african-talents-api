import os
import uuid

from django.conf import settings
from django.db import models

from apps.core.models import SoftDeleteModel


def upload_path(instance, filename):
    """Nom de fichier régénéré (jamais le nom fourni par l'utilisateur) : <uuid>.<ext>."""
    ext = os.path.splitext(filename)[1].lower()
    return f"uploads/{instance.created_at_bucket()}/{uuid.uuid4()}{ext}"


class MediaAsset(SoftDeleteModel):
    KIND_IMAGE = "image"
    KIND_DOCUMENT = "document"
    KIND_CHOICES = [(KIND_IMAGE, "Image"), (KIND_DOCUMENT, "Document")]

    file = models.FileField(upload_to=upload_path, max_length=300)
    original_name = models.CharField(max_length=255)
    kind = models.CharField(max_length=16, choices=KIND_CHOICES)
    mime_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    usage = models.CharField(max_length=64, blank=True)  # ex. "candidate_photo", "news_main_image"
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="uploaded_media"
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name

    def created_at_bucket(self):
        from django.utils import timezone

        return timezone.now().strftime("%Y/%m")

    @property
    def size_kb(self):
        return round(self.size_bytes / 1024)
