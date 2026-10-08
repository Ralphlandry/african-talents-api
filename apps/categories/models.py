from django.db import models

from apps.core.models import SoftDeleteModel


class Category(SoftDeleteModel):
    DRAFT = "draft"
    PUBLISHED = "published"
    STATUS_CHOICES = [(DRAFT, "Brouillon"), (PUBLISHED, "Publiée")]

    competition = models.ForeignKey(
        "competition.Competition", on_delete=models.CASCADE, related_name="categories", null=True, blank=True
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=32, blank=True)
    image = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    order = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT, db_index=True)

    class Meta:
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["competition", "slug"], name="unique_category_slug_per_competition")
        ]

    def __str__(self):
        return self.name
