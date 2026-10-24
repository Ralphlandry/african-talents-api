
import secrets

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class VotePackage(BaseModel):
    """
    Forfait de vote défini par l'administrateur : quantité de votes + prix (décision B).
    Il n'existe AUCUN prix unitaire global codé en dur — chaque forfait fixe librement
    son propre couple (quantité, prix). L'API de paiement calcule toujours le montant
    à partir du forfait choisi, jamais à partir d'une valeur envoyée par le client.
    """

    competition = models.ForeignKey("competition.Competition", on_delete=models.CASCADE, related_name="vote_packages")
    label = models.CharField(max_length=80)  # ex. "10 votes", "Pack Soutien"
    quantity = models.PositiveIntegerField()
    price_xaf = models.PositiveIntegerField()  # XAF n'a pas de décimales
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["competition", "order", "quantity"]

    def __str__(self):
        return f"{self.label} ({self.quantity} votes — {self.price_xaf} FCFA)"


class VoteOrder(BaseModel):
    """
    Commande de vote créée par un visiteur. Reflète TOUJOURS un VotePackage existant au
    moment de la commande : quantité et montant sont copiés (jamais recalculés depuis une
    valeur envoyée par le client), pour que la commande reste correcte même si le forfait
    est modifié ou désactivé plus tard.
    """

    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    STATUS_CHOICES = [
        (PENDING, "En attente"), (PAID, "Payée"), (FAILED, "Échouée"),
        (CANCELLED, "Annulée"), (EXPIRED, "Expirée"),
    ]

    order_number = models.CharField(max_length=32, unique=True, editable=False)
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="vote_orders")
    vote_package = models.ForeignKey(VotePackage, on_delete=models.PROTECT, related_name="orders")
    phase = models.ForeignKey(
        "competition.Phase", on_delete=models.SET_NULL, null=True, blank=True, related_name="vote_orders"
    )
    # Copiés depuis le forfait au moment de la commande (snapshot immuable).
    quantity = models.PositiveIntegerField()
    amount_xaf = models.PositiveIntegerField()
    customer_phone = models.CharField(max_length=32)
    operator = models.CharField(max_length=32)  # MTN | ORANGE
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    idempotency_key = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_order_number():
        from django.utils import timezone

        year = timezone.now().year
        seq = VoteOrder.objects.filter(order_number__startswith=f"AT-{year}-").count() + 1
        candidate_number = f"AT-{year}-{seq:06d}-{secrets.token_hex(6).upper()}"
        while VoteOrder.objects.filter(order_number=candidate_number).exists():
            candidate_number = f"AT-{year}-{seq:06d}-{secrets.token_hex(6).upper()}"
        return candidate_number


class Vote(BaseModel):
    """
    Ligne du grand livre des votes. C'est la SEULE source de vérité pour les totaux et le
    classement — jamais un compteur dénormalisé sur Candidate. Une ligne PAID est liée à
    une VoteOrder unique (contrainte OneToOne) : impossible de créditer deux fois la même
    commande.
    """

    PAID = "PAID"
    FREE = "FREE"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    SOURCE_CHOICES = [(PAID, "Payé"), (FREE, "Gratuit"), (MANUAL_ADJUSTMENT, "Ajustement manuel")]

    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="votes")
    phase = models.ForeignKey(
        "competition.Phase", on_delete=models.SET_NULL, null=True, blank=True, related_name="votes"
    )
    quantity = models.IntegerField()  # peut être négatif pour un ajustement manuel de correction
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True)
    vote_order = models.OneToOneField(
        VoteOrder, on_delete=models.PROTECT, null=True, blank=True, related_name="vote"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    reason = models.CharField(max_length=255, blank=True)  # obligatoire en pratique pour un ajustement manuel

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["candidate", "phase"])]

    def __str__(self):
        return f"{self.candidate} +{self.quantity} ({self.source})"
