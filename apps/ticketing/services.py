from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record
from apps.competition.models import Competition
from apps.core.exceptions import ConflictError

from .models import TicketOrder


@transaction.atomic
def set_ticket_sales_open(*, competition_id, is_open, actor, request=None):
    competition = Competition.objects.select_for_update().get(pk=competition_id)
    competition.ticket_sales_open = is_open
    competition.save(update_fields=["ticket_sales_open", "updated_at"])
    record(
        request=request,
        actor=actor,
        action=A.TICKET_SALES_STATUS_CHANGED,
        module=M.TICKETING,
        resource="competition",
        resource_id=competition.pk,
        metadata={"ticket_sales_open": is_open},
    )
    return competition


@transaction.atomic
def create_ticket_order(*, ticket_type, first_name, last_name, phone, operator, promo_candidate,
                        idempotency_key, request=None):
    competition = Competition.objects.select_for_update().get(pk=ticket_type.competition_id)
    if not competition.ticket_sales_open:
        raise ValidationError({"ticket_type": "La vente des billets est actuellement fermée."})

    defaults = {
        "ticket_type": ticket_type,
        "buyer_first_name": first_name,
        "buyer_last_name": last_name,
        "customer_phone": phone,
        "amount_xaf": ticket_type.price_xaf,
        "operator": operator,
        "promo_candidate": promo_candidate,
    }
    order, created = TicketOrder.objects.get_or_create(idempotency_key=idempotency_key, defaults=defaults)
    if not created:
        same_request = (
            order.ticket_type_id == ticket_type.id
            and order.buyer_first_name == first_name
            and order.buyer_last_name == last_name
            and order.customer_phone == phone
            and order.operator == operator
            and order.promo_candidate_id == getattr(promo_candidate, "id", None)
        )
        if not same_request:
            raise ConflictError(
                "Cette clé de commande a déjà été utilisée avec d'autres informations.",
                code="IDEMPOTENCY_KEY_REUSED",
            )
        return order, False

    record(
        request=request,
        action=A.TICKET_ORDER_CREATED,
        module=M.TICKETING,
        resource="ticket_order",
        resource_id=order.pk,
        metadata={
            "order_number": order.order_number,
            "ticket_class": ticket_type.ticket_class,
            "amount_xaf": order.amount_xaf,
            "candidate_code": (promo_candidate.promo_code or promo_candidate.code) if promo_candidate else None,
        },
    )
    return order, True
