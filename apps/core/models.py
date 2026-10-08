import uuid

from django.db import models
from django.utils import timezone


class BaseModel(models.Model):
    """Base commune : clé primaire UUID + horodatage."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class SoftDeleteModel(BaseModel):
    """Suppression logique (contenu éditorial uniquement, jamais paiements/votes/audit)."""

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])


class SiteSettings(models.Model):
    """
    Paramètres généraux du site (singleton — une seule ligne, id=1).
    Les paramètres de paiement (prix du vote) ne sont PAS ici : l'admin définit des
    forfaits de vote (quantité + prix) via le modèle VotePackage du jalon 3.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    # Général
    site_name = models.CharField(max_length=160, default="African Talents")
    tagline = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    logo = models.ForeignKey("media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    favicon = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    # Réseaux sociaux
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    youtube_url = models.URLField(blank=True)

    # Contact
    contact_phone = models.CharField(max_length=32, blank=True)
    contact_phone_2 = models.CharField(max_length=32, blank=True)
    contact_whatsapp = models.CharField(max_length=32, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_address = models.CharField(max_length=255, blank=True)

    # Statistiques affichées sur le site public (ex. "300 talents", "20 pays")
    stats = models.JSONField(default=list, blank=True)  # [{"label": "...", "value": "..."}]

    class Meta:
        verbose_name = "Paramètres du site"
        verbose_name_plural = "Paramètres du site"

    def __str__(self):
        return "Paramètres du site"

    def save(self, *args, **kwargs):
        self.pk = 1  # force le singleton, quoi qu'il arrive
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
