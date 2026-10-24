from django.db import models

from apps.core.models import BaseModel


class Advertisement(BaseModel):
    HOME = "home"
    TICKETING = "ticketing"
    BOTH = "both"
    PLACEMENT_CHOICES = [
        (HOME, "Accueil"),
        (TICKETING, "Billetterie"),
        (BOTH, "Accueil et billetterie"),
    ]

    title = models.CharField(max_length=160)
    image = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.PROTECT, related_name="advertisements"
    )
    placement = models.CharField(max_length=16, choices=PLACEMENT_CHOICES, default=BOTH, db_index=True)
    display_delay_seconds = models.PositiveIntegerField(default=10)
    dismissal_cooldown_hours = models.PositiveIntegerField(default=24)
    button_label = models.CharField(max_length=80, default="Acheter maintenant")
    button_url = models.CharField(max_length=500, default="/billetterie")
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title
