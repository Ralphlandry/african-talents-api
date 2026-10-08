from django.conf import settings
from django.db import models

from apps.core.models import SoftDeleteModel


class NewsPost(SoftDeleteModel):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    STATUS_CHOICES = [
        (DRAFT, "Brouillon"), (SCHEDULED, "Programmé"), (PUBLISHED, "Publié"), (ARCHIVED, "Archivé"),
    ]

    title = models.CharField(max_length=220)
    slug = models.SlugField(max_length=240, unique=True)
    excerpt = models.CharField(max_length=400, blank=True)
    content_html = models.TextField(blank=True)  # assaini avant sauvegarde, cf. services.py
    main_image = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    category = models.ForeignKey(
        "categories.Category", on_delete=models.SET_NULL, null=True, blank=True, related_name="news_posts"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="news_posts"
    )
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-published_at"])]

    def __str__(self):
        return self.title
