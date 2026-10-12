import secrets

from django.db import models

from apps.core.models import BaseModel


def generate_order_number():
    return secrets.token_hex(16)


def generate_ticket_code():
    return f"AT-{secrets.token_hex(6).upper()}"


class TicketType(BaseModel):
    CLASSIC = "CLASSIC"
    VIP = "VIP"
    TYPE_CHOICES = [(CLASSIC, "Classique"), (VIP, "VIP")]

    competition = models.ForeignKey("competition.Competition", on_delete=models.CASCADE, related_name="ticket_types")
    ticket_class = models.CharField(max_length=12, choices=TYPE_CHOICES)
    label = models.CharField(max_length=80)
    price_xaf = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["ticket_class"]
        constraints = [
            models.UniqueConstraint(fields=["competition", "ticket_class"], name="unique_ticket_class_per_competition"),
        ]

    def __str__(self):
        return f"{self.label} — {self.price_xaf} FCFA"


class TicketOrder(BaseModel):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    REFUNDED = "REFUNDED"
    STATUS_CHOICES = [
        (PENDING, "En attente"),
        (PAID, "Payé"),
        (FAILED, "Échoué"),
        (CANCELLED, "Annulé"),
        (EXPIRED, "Expiré"),
        (REFUNDED, "Remboursé"),
    ]

    order_number = models.CharField(max_length=32, unique=True, default=generate_order_number, editable=False)
    ticket_code = models.CharField(max_length=15, unique=True, default=generate_ticket_code, editable=False)
    ticket_type = models.ForeignKey(TicketType, on_delete=models.PROTECT, related_name="orders")
    promo_candidate = models.ForeignKey(
        "candidates.Candidate", on_delete=models.SET_NULL, null=True, blank=True, related_name="ticket_orders"
    )
    buyer_first_name = models.CharField(max_length=100)
    buyer_last_name = models.CharField(max_length=100)
    customer_phone = models.CharField(max_length=32)
    amount_xaf = models.PositiveIntegerField()
    operator = models.CharField(max_length=16, choices=[("MTN", "MTN Mobile Money"), ("ORANGE", "Orange Money")])
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    idempotency_key = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "-created_at"])]

    def __str__(self):
        return self.order_number
