from django.db import models

from apps.core.models import SoftDeleteModel


class TeamMember(SoftDeleteModel):
    TEAM = "team"
    COACH = "coach"
    TYPE_CHOICES = [(TEAM, "Équipe"), (COACH, "Coach")]

    type = models.CharField(max_length=16, choices=TYPE_CHOICES, db_index=True)
    full_name = models.CharField(max_length=160)
    role_title = models.CharField(max_length=160, blank=True)  # ex. "Coach chant", "Responsable partenariats"
    bio = models.TextField(blank=True)
    photo = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    order = models.PositiveSmallIntegerField(default=1)
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ["type", "order", "full_name"]

    def __str__(self):
        return f"{self.full_name} ({self.get_type_display()})"
