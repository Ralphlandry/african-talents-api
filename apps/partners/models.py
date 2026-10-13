from django.db import models

from apps.core.models import SoftDeleteModel


class Partner(SoftDeleteModel):
    name = models.CharField(max_length=160)
    logo = models.ForeignKey(
        "media_library.MediaAsset", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    order = models.PositiveSmallIntegerField(default=1)
    is_visible = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "name"]

    def __str__(self):
        return self.name
