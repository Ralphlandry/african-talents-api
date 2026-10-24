from django.db import models

from apps.core.models import SoftDeleteModel


class Candidate(SoftDeleteModel):
    DRAFT = "draft"
    PENDING = "pending"
    PUBLISHED = "published"
    STATUS_CHOICES = [(DRAFT, "Brouillon"), (PENDING, "En attente"), (PUBLISHED, "Publié")]

    competition = models.ForeignKey("competition.Competition", on_delete=models.CASCADE, related_name="candidates")
    category = models.ForeignKey("categories.Category", on_delete=models.PROTECT, related_name="candidates")
    current_phase = models.ForeignKey(
        "competition.Phase", on_delete=models.SET_NULL, null=True, blank=True, related_name="candidates"
    )
    code = models.CharField(max_length=32)  # ex. "AT-001", unique par compétition
    promo_code = models.CharField(max_length=32, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=220)
    bio = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    photo = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    gallery = models.ManyToManyField("media_library.MediaAsset", blank=True, related_name="+")
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    is_active = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(fields=["competition", "code"], name="unique_candidate_code_per_competition"),
            models.UniqueConstraint(fields=["competition", "slug"], name="unique_candidate_slug_per_competition"),
        ]
        indexes = [models.Index(fields=["competition", "status", "is_active"])]

    def __str__(self):
        return f"{self.code} — {self.last_name} {self.first_name}"

    @property
    def display_name(self):
        return f"{self.last_name} {self.first_name}"
