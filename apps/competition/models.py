from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class Competition(BaseModel):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    ENDED = "ENDED"
    STATUS_CHOICES = [
        (DRAFT, "Brouillon"), (SCHEDULED, "Programmée"), (ACTIVE, "Active"),
        (SUSPENDED, "Suspendue"), (ENDED, "Terminée"),
    ]

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    votes_open = models.BooleanField(default=False)
    # Une seule compétition peut être "active" à la fois (contrainte applicative, cf. services.py).
    is_current = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit être postérieure à la date de début."})


class Phase(BaseModel):
    SELECTION = "a_venir"
    ACTIVE = "active"
    ENDED = "terminee"
    STATUS_CHOICES = [(SELECTION, "À venir"), (ACTIVE, "En cours"), (ENDED, "Terminée")]

    competition = models.ForeignKey(Competition, on_delete=models.CASCADE, related_name="phases")
    name = models.CharField(max_length=120)
    order = models.PositiveSmallIntegerField(default=1)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=SELECTION)

    class Meta:
        ordering = ["competition", "order"]
        constraints = [models.UniqueConstraint(fields=["competition", "order"], name="unique_phase_order")]

    def __str__(self):
        return f"{self.competition.name} — {self.name}"

    def clean(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "La date de fin doit être postérieure à la date de début."})
