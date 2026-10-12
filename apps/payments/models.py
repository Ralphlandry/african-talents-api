from django.db import models

from apps.core.models import BaseModel


class Payment(BaseModel):
    """
    Reflète l'état du paiement HR-Skills Pay pour une commande de vote ou de billet. Machine à états monotone :
    un état terminal (SUCCESS, FAILED, CANCELLED, EXPIRED, REFUNDED) ne redevient jamais
    PENDING — cf. apps/payments/services.py::apply_status pour les transitions autorisées.
    """

    PENDING = "PENDING"
    HOLD = "HOLD"  # revue anti-blanchiment côté prestataire, non terminal
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"
    STATUS_CHOICES = [
        (PENDING, "En attente"), (HOLD, "En revue"), (SUCCESS, "Réussi"), (FAILED, "Échoué"),
        (CANCELLED, "Annulé"), (EXPIRED, "Expiré"), (REFUNDED, "Remboursé"),
    ]
    TERMINAL_STATUSES = {SUCCESS, FAILED, CANCELLED, EXPIRED, REFUNDED}

    vote_order = models.OneToOneField(
        "voting.VoteOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="payment"
    )
    ticket_order = models.OneToOneField(
        "ticketing.TicketOrder", on_delete=models.PROTECT, null=True, blank=True, related_name="payment"
    )
    reference = models.CharField(max_length=32, unique=True)  # = order_number
    provider = models.CharField(max_length=32, default="hrskills_pay")
    provider_reference = models.CharField(max_length=100, blank=True)
    checkout_url = models.URLField(max_length=1000, blank=True)
    environment = models.CharField(max_length=8)  # "test" | "live"
    amount_xaf = models.PositiveIntegerField()
    currency = models.CharField(max_length=3, default="XAF")
    phone = models.CharField(max_length=32, blank=True)
    operator = models.CharField(max_length=32)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    fees_xaf = models.PositiveIntegerField(null=True, blank=True)
    net_amount_xaf = models.PositiveIntegerField(null=True, blank=True)
    failure_reason = models.CharField(max_length=255, blank=True)
    initiated_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-initiated_at"]
        indexes = [models.Index(fields=["status", "-initiated_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(vote_order__isnull=False, ticket_order__isnull=True)
                    | models.Q(vote_order__isnull=True, ticket_order__isnull=False)
                ),
                name="payment_has_exactly_one_order",
            ),
        ]

    def __str__(self):
        return f"{self.reference} — {self.status}"

    @property
    def is_terminal(self):
        return self.status in self.TERMINAL_STATUSES


class PaymentEvent(BaseModel):
    """Trace brute de chaque webhook reçu (avant/après traitement), pour audit et déduplication."""

    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True, related_name="events")
    reference = models.CharField(max_length=32, blank=True, db_index=True)  # tel que reçu, même si Payment introuvable
    provider_event_id = models.CharField(max_length=150, unique=True)  # id fourni par le prestataire, sinon empreinte du corps
    event_type = models.CharField(max_length=64, blank=True)
    raw_payload = models.JSONField(default=dict)
    signature_valid = models.BooleanField()
    processed = models.BooleanField(default=False)
    processing_error = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} ({self.reference})"
