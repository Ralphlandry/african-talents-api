import hashlib
import json
import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record
from apps.core.exceptions import ConflictError, DomainError, ServiceUnavailableError
from apps.ticketing.models import TicketOrder
from apps.voting.models import VoteOrder
from apps.voting.services import credit_paid_order

from .gateway import PaymentGatewayError, build_client_from_settings, card_payments_enabled, verify_webhook_signature
from .models import Payment, PaymentEvent

logger = logging.getLogger(__name__)
STATUS_SYNC_CACHE_SECONDS = 10


def _mobile_money_phone_number(phone):
    if phone.startswith("+237"):
        return phone[4:]
    if phone.startswith("00237"):
        return phone[5:]
    if phone.startswith("237") and len(phone) == 12:
        return phone[3:]
    return phone


def _provider_failure_reason(verified, fallback):
    raw = verified.get("raw")
    if not isinstance(raw, dict):
        return fallback
    data = raw.get("data")
    sources = (data, raw) if isinstance(data, dict) else (raw,)
    for source in sources:
        for field in ("failure_reason", "decline_reason", "error_description", "error_message", "reason"):
            value = source.get(field)
            if isinstance(value, str) and value.strip():
                return value.strip()[:255]
    return fallback


# Transitions autorisées (machine à états monotone — un état terminal ne redevient jamais actif).
_ALLOWED_TRANSITIONS = {
    Payment.PENDING: {Payment.SUCCESS, Payment.FAILED, Payment.CANCELLED, Payment.EXPIRED, Payment.HOLD},
    Payment.HOLD: {Payment.SUCCESS, Payment.FAILED},
    Payment.SUCCESS: {Payment.REFUNDED},
    Payment.FAILED: {Payment.SUCCESS},
    Payment.CANCELLED: set(),
    Payment.EXPIRED: set(),
    Payment.REFUNDED: set(),
}


def _order_status_for(payment_status):
    return {
        Payment.SUCCESS: VoteOrder.PAID,
        Payment.FAILED: VoteOrder.FAILED,
        Payment.CANCELLED: VoteOrder.CANCELLED,
        Payment.EXPIRED: VoteOrder.EXPIRED,
    }.get(payment_status)


def _ticket_status_for(payment_status):
    return {
        Payment.SUCCESS: TicketOrder.PAID,
        Payment.FAILED: TicketOrder.FAILED,
        Payment.CANCELLED: TicketOrder.CANCELLED,
        Payment.EXPIRED: TicketOrder.EXPIRED,
        Payment.REFUNDED: TicketOrder.REFUNDED,
    }.get(payment_status)


# ---------------------------------------------------------------------------
# Initiation (création de la ligne PENDING en base, puis appel réseau HORS transaction)
# ---------------------------------------------------------------------------


def initiate_payment(order, *, request=None):
    """
    Crée le Payment (PENDING) puis appelle HR-Skills Pay. L'appel réseau se fait
    délibérément APRÈS le commit de la ligne PENDING (jamais dans une transaction DB
    ouverte) pour ne pas bloquer de verrous pendant un aller-retour réseau.
    """
    from django.conf import settings

    is_ticket_order = isinstance(order, TicketOrder)
    is_card = order.operator == "CARD"
    if is_card and not card_payments_enabled():
        raise ServiceUnavailableError("Le paiement par carte est désactivé.", code="CARD_PAYMENTS_DISABLED")

    payment = Payment.objects.create(
        vote_order=None if is_ticket_order else order,
        ticket_order=order if is_ticket_order else None,
        reference=order.order_number, environment=settings.HRSKILLS_ENVIRONMENT,
        amount_xaf=order.amount_xaf, phone=order.customer_phone, operator=order.operator,
    )
    description = (
        f"African Talents — billet {order.ticket_type.label}"
        if is_ticket_order
        else f"African Talents — {order.quantity} votes"
    )
    metadata = {"order_number": order.order_number}
    if is_ticket_order:
        metadata.update({"ticket_class": order.ticket_type.ticket_class})
        if order.promo_candidate_id:
            metadata["candidate_code"] = order.promo_candidate.promo_code or order.promo_candidate.code
    else:
        metadata["candidate_code"] = order.candidate.code

    try:
        client = build_client_from_settings()
        if is_card:
            return_url = _card_return_url(settings.HRSKILLS_CARD_RETURN_URL, order.order_number)
            cancel_url = _card_return_url(settings.HRSKILLS_CARD_RETURN_URL, order.order_number, cancelled=True)
            result = client.create_card_payment(
                amount_xaf=order.amount_xaf,
                description=description,
                customer={"phone": order.customer_phone} if order.customer_phone else {},
                currency="XAF",
                return_url=return_url,
                cancel_url=cancel_url,
                lang="fr",
                idempotency_key=order.idempotency_key,
            )
        else:
            result = client.create_mobile_money_payin(
                reference=order.order_number, amount_xaf=order.amount_xaf,
                phone_number=_mobile_money_phone_number(order.customer_phone),
                operator=order.operator, description=description, metadata=metadata,
                idempotency_key=order.idempotency_key,
            )
    except PaymentGatewayError as exc:
        if exc.code == "NETWORK_ERROR" or (exc.status_code is not None and exc.status_code >= 500):
            logger.warning(
                "Résultat d'initiation incertain pour %s; la commande reste en attente pour vérification.",
                order.order_number,
            )
        else:
            _mark_initiation_failed(payment, order, str(exc), request=request)
        raise ServiceUnavailableError(
            "Le paiement n'a pas pu être initié auprès du prestataire. Veuillez réessayer.",
            code="PAYMENT_INITIATION_FAILED",
        ) from exc
    except Exception as exc:  # config manquante, etc. — jamais laisser fuiter le détail au client
        logger.exception("Erreur inattendue à l'initiation du paiement %s", order.order_number)
        logger.warning(
            "Résultat d'initiation incertain pour %s; la commande reste en attente pour vérification.",
            order.order_number,
        )
        raise ServiceUnavailableError("Service de paiement indisponible pour le moment.", code="PAYMENT_SERVICE_DOWN") from exc

    with transaction.atomic():
        payment.provider_reference = result.get("provider_reference") or ""
        if is_card:
            payment.provider = "hrskills_pay_card"
            payment.checkout_url = result.get("checkout_url") or ""
        gateway_status = (result.get("status") or "").upper()
        if is_card:
            gateway_status = _normalize_card_status(gateway_status)
        if gateway_status in (Payment.SUCCESS, Payment.FAILED, Payment.CANCELLED, Payment.EXPIRED):
            apply_status(payment, gateway_status, reason="Statut terminal immédiat du prestataire.", request=request)
        payment.save(update_fields=["provider", "provider_reference", "checkout_url", "updated_at"])
        record(request=request, action=A.PAYMENT_INITIATED, module=M.FINANCE, resource="payment",
               resource_id=payment.pk, metadata={"reference": payment.reference, "provider_reference": payment.provider_reference})

    return payment


def _card_return_url(base_url, order_number, *, cancelled=False):
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["order_number"] = order_number
    if cancelled:
        query["cancelled"] = "1"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _normalize_card_status(status):
    return {
        "CAPTURED": Payment.SUCCESS,
        "SETTLED": Payment.SUCCESS,
        "CANCELED": Payment.CANCELLED,
    }.get(status, status)


def _mark_initiation_failed(payment, order, reason, *, request=None):
    with transaction.atomic():
        payment.status = Payment.FAILED
        payment.failure_reason = reason[:255]
        payment.confirmed_at = timezone.now()
        payment.save(update_fields=["status", "failure_reason", "confirmed_at", "updated_at"])
        order.status = order.FAILED
        order.save(update_fields=["status", "updated_at"])
        record(request=request, action=A.PAYMENT_INITIATION_FAILED, module=M.FINANCE, resource="payment",
               resource_id=payment.pk, metadata={"reference": payment.reference, "reason": reason})


# ---------------------------------------------------------------------------
# Transition d'état (utilisée par le webhook ET par la resynchronisation manuelle)
# ---------------------------------------------------------------------------


@transaction.atomic
def apply_status(
    payment, new_status, *, reason="", fees_xaf=None, net_amount_xaf=None, request=None, actor=None, vote_reason=""
):
    if new_status == payment.status:
        return payment  # idempotent : rejouer le même statut ne fait rien
    allowed = _ALLOWED_TRANSITIONS.get(payment.status, set())
    if new_status not in allowed:
        raise ConflictError(
            f"Transition de paiement refusée : {payment.status} → {new_status}.", code="ILLEGAL_STATUS_TRANSITION"
        )

    payment.status = new_status
    if fees_xaf is not None:
        payment.fees_xaf = fees_xaf
    if net_amount_xaf is not None:
        payment.net_amount_xaf = net_amount_xaf
    if new_status in Payment.TERMINAL_STATUSES:
        payment.confirmed_at = timezone.now()
    if new_status == Payment.FAILED:
        payment.failure_reason = reason[:255]
    elif new_status == Payment.SUCCESS:
        payment.failure_reason = ""
    payment.save()

    order_status = _order_status_for(new_status)
    if order_status and payment.vote_order_id:
        payment.vote_order.status = order_status
        payment.vote_order.save(update_fields=["status", "updated_at"])
    ticket_status = _ticket_status_for(new_status)
    if ticket_status and payment.ticket_order_id:
        payment.ticket_order.status = ticket_status
        payment.ticket_order.save(update_fields=["status", "updated_at"])

    if new_status == Payment.SUCCESS and payment.vote_order_id:
        credit_paid_order(payment.vote_order, reason=vote_reason)

    record(request=request, actor=actor, action=A.PAYMENT_STATUS_CHANGED, module=M.FINANCE, resource="payment",
           resource_id=payment.pk, metadata={"reference": payment.reference, "status": new_status, "reason": reason})
    return payment


def refresh_pending_payment(payment, *, request=None):
    if payment.status not in (Payment.PENDING, Payment.FAILED):
        return payment
    if payment.provider == "hrskills_pay_card" and not payment.provider_reference:
        return payment

    if not cache.add(f"payment-status-sync:{payment.reference}", True, STATUS_SYNC_CACHE_SECONDS):
        return payment

    try:
        client = build_client_from_settings()
        if payment.provider == "hrskills_pay_card":
            verified = client.get_card_payment_status(payment.provider_reference)
            status = _normalize_card_status((verified.get("status") or "").upper())
        else:
            verified = client.get_payment_status(payment.reference)
            status = (verified.get("status") or "").upper()
    except PaymentGatewayError as exc:
        logger.warning("Impossible de synchroniser le paiement %s auprès de HR-Skills Pay : %s", payment.reference, exc)
        return payment

    if status not in (Payment.SUCCESS, Payment.FAILED, Payment.CANCELLED, Payment.EXPIRED):
        return payment

    amount_xaf = verified.get("amount_xaf")
    if amount_xaf is not None and int(amount_xaf) != payment.amount_xaf:
        logger.error(
            "Écart de montant pendant la synchronisation de %s : attendu %s, reçu %s — paiement non crédité.",
            payment.reference, payment.amount_xaf, amount_xaf,
        )
        return payment
    verified_currency = verified.get("currency")
    if verified_currency and verified_currency.upper() != payment.currency:
        logger.error(
            "Écart de devise pendant la synchronisation de %s : attendu %s, reçu %s — paiement non crédité.",
            payment.reference, payment.currency, verified_currency,
        )
        return payment

    return apply_status(
        payment,
        status,
        fees_xaf=verified.get("fees_xaf"),
        net_amount_xaf=verified.get("net_amount_xaf"),
        reason=(
            _provider_failure_reason(verified, "Paiement refusé par le prestataire.")
            if status == Payment.FAILED
            else "Statut confirmé par resynchronisation HR-Skills Pay."
        ),
        request=request,
    )


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


def handle_webhook(raw_body: bytes, signature_header: str, *, request=None):
    from django.conf import settings

    signature_valid = bool(settings.HRSKILLS_WEBHOOK_SECRET) and verify_webhook_signature(
        raw_body, signature_header, settings.HRSKILLS_WEBHOOK_SECRET
    )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        payload = {}

    event_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    event_id = payload.get("event_id") or event_data.get("event_id") or f"sha256:{hashlib.sha256(raw_body).hexdigest()}"
    reference = payload.get("reference") or event_data.get("reference", "")
    event_type = payload.get("event_type") or payload.get("type") or event_data.get("event_type", "")

    if not signature_valid:
        PaymentEvent.objects.get_or_create(
            provider_event_id=event_id,
            defaults={"reference": reference, "event_type": event_type, "raw_payload": payload, "signature_valid": False},
        )
        record(request=request, action=A.PAYMENT_WEBHOOK_REJECTED, module=M.FINANCE, resource="payment_event",
               metadata={"reference": reference, "reason": "invalid_signature"})
        raise DomainError("Signature invalide.", code="INVALID_SIGNATURE")

    event, created = PaymentEvent.objects.get_or_create(
        provider_event_id=event_id,
        defaults={"reference": reference, "event_type": event_type, "raw_payload": payload, "signature_valid": True},
    )
    if not created:
        return event  # déjà traité (rejeu du même événement) — on répond 200 sans retraiter

    record(request=request, action=A.PAYMENT_WEBHOOK_RECEIVED, module=M.FINANCE, resource="payment_event",
           resource_id=event.pk, metadata={"reference": reference, "event_type": event_type})

    try:
        _process_event(event, payload)
    except Exception as exc:  # ne jamais faire échouer la réponse HTTP au prestataire pour une erreur de traitement
        logger.exception("Échec de traitement du webhook %s (%s)", event_id, reference)
        event.processing_error = str(exc)[:255]
        event.save(update_fields=["processing_error"])
    else:
        event.processed = True
        event.save(update_fields=["processed"])
    return event


def _process_event(event, payload):
    event_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    reference = payload.get("reference") or event_data.get("reference", "")
    payment = (
        Payment.objects.select_related("vote_order", "vote_order__candidate", "ticket_order", "ticket_order__promo_candidate")
        .filter(reference=reference)
        .first()
    )
    if payment is None:
        payment = (
            Payment.objects.select_related("vote_order", "vote_order__candidate", "ticket_order", "ticket_order__promo_candidate")
            .filter(provider_reference=reference, provider="hrskills_pay_card")
            .first()
        )
    if payment is None:
        logger.warning("Webhook reçu pour une référence inconnue : %s", reference)
        return
    event.payment = payment
    event.save(update_fields=["payment"])

    if payment.is_terminal and payment.status != Payment.FAILED:
        return  # sécurité supplémentaire : un événement tardif ne peut pas rouvrir un paiement terminé

    # Défense en profondeur : on ne fait jamais confiance au seul contenu du webhook,
    # on revérifie le statut auprès de l'API de statut avant d'appliquer quoi que ce soit.
    try:
        client = build_client_from_settings()
        if payment.provider == "hrskills_pay_card":
            verified = client.get_card_payment_status(payment.provider_reference)
            verified_status = _normalize_card_status((verified.get("status") or "").upper())
        else:
            verified = client.get_payment_status(reference)
            verified_status = (verified.get("status") or "").upper()
    except PaymentGatewayError as exc:
        logger.error("Impossible de revérifier le paiement %s auprès de HR-Skills Pay : %s", reference, exc)
        return

    verified_amount = verified.get("amount_xaf")
    if verified_amount is not None and int(verified_amount) != payment.amount_xaf:
        logger.error(
            "Écart de montant sur %s : attendu %s, reçu %s — paiement NON crédité.",
            reference, payment.amount_xaf, verified_amount,
        )
        return
    verified_currency = verified.get("currency")
    if verified_currency and verified_currency.upper() != payment.currency:
        logger.error(
            "Écart de devise sur %s : attendu %s, reçu %s — paiement NON crédité.",
            reference, payment.currency, verified_currency,
        )
        return
    if verified_status not in dict(Payment.STATUS_CHOICES):
        logger.warning("Statut inconnu renvoyé par HR-Skills Pay pour %s : %r", reference, verified_status)
        return

    apply_status(
        payment, verified_status,
        fees_xaf=verified.get("fees_xaf"), net_amount_xaf=verified.get("net_amount_xaf"),
        reason=(
            _provider_failure_reason(verified, f"webhook:{event.event_type or event_data.get('event_type', '')}")
            if verified_status == Payment.FAILED
            else f"webhook:{event.event_type or event_data.get('event_type', '')}"
        ),
    )


# ---------------------------------------------------------------------------
# Filet de sécurité : expiration des paiements PENDING trop anciens (webhook jamais reçu)
# ---------------------------------------------------------------------------


def expire_stale_pending_payments():
    from django.conf import settings

    cutoff = timezone.now() - timezone.timedelta(minutes=settings.HRSKILLS_PENDING_TIMEOUT_MINUTES)
    stale = Payment.objects.filter(status=Payment.PENDING, initiated_at__lt=cutoff).select_related(
        "vote_order", "ticket_order"
    )
    count = 0
    for payment in stale:
        apply_status(payment, Payment.EXPIRED, reason="Délai d'attente dépassé (webhook jamais reçu).")
        count += 1
    if count:
        record(action=A.PAYMENT_EXPIRED, module=M.FINANCE, resource="payment", metadata={"count": count})
    return count


# ---------------------------------------------------------------------------
# Remboursement (n'annule PAS les votes déjà crédités : un ajustement manuel séparé
# via apps.voting.services.adjust_votes reste la façon explicite de les retirer si besoin)
# ---------------------------------------------------------------------------


def refund_payment(actor, payment, *, request=None):
    if payment.status != Payment.SUCCESS:
        raise ConflictError("Seul un paiement réussi peut être remboursé.", code="NOT_REFUNDABLE")
    try:
        client = build_client_from_settings()
        client.refund_payment(payment.reference)
    except PaymentGatewayError as exc:
        raise ServiceUnavailableError(f"Échec du remboursement auprès du prestataire : {exc}", code="REFUND_FAILED") from exc

    apply_status(payment, Payment.REFUNDED, reason="Remboursement manuel par un administrateur.", request=request)
    record(request=request, actor=actor, action=A.PAYMENT_REFUNDED, module=M.FINANCE, resource="payment",
           resource_id=payment.pk, metadata={"reference": payment.reference})
    return payment
