import logging

from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record
from apps.core.exceptions import ServiceUnavailableError
from apps.payments.gateway import PaymentGatewayError, build_client_from_settings
from apps.payments.models import Payment

from .models import ReconciliationItem, ReconciliationRun

logger = logging.getLogger(__name__)

MERCHANT_CACHE_KEY = "finance:merchant_account"
MERCHANT_CACHE_TTL = 120  # secondes — évite de solliciter HR-Skills Pay à chaque rafraîchissement d'écran


# ---------------------------------------------------------------------------
# Vue d'ensemble
# ---------------------------------------------------------------------------


def overview():
    successful = Payment.objects.filter(status=Payment.SUCCESS)
    total_collected = successful.aggregate(total=Sum("amount_xaf"))["total"] or 0
    total_fees = successful.aggregate(total=Sum("fees_xaf"))["total"] or 0
    counts = Payment.objects.aggregate(
        successful=Count("id", filter=Q(status=Payment.SUCCESS)),
        pending=Count("id", filter=Q(status__in=[Payment.PENDING, Payment.HOLD])),
        failed=Count("id", filter=Q(status__in=[Payment.FAILED, Payment.CANCELLED, Payment.EXPIRED])),
    )
    since = timezone.now() - timezone.timedelta(days=180)
    trend = (
        successful.filter(confirmed_at__gte=since)
        .annotate(month=TruncMonth("confirmed_at"))
        .values("month")
        .annotate(amount=Sum("amount_xaf"))
        .order_by("month")
    )
    return {
        "total_collected_xaf": total_collected,
        "net_amount_xaf": total_collected - total_fees,
        "successful_payments": counts["successful"],
        "pending_payments": counts["pending"],
        "failed_payments": counts["failed"],
        "monthly_trend": [{"month": row["month"].strftime("%Y-%m"), "amount_xaf": row["amount"] or 0} for row in trend],
    }


# ---------------------------------------------------------------------------
# Compte marchand HR-Skills Pay (lecture seule, en cache court — jamais la source de vérité comptable)
# ---------------------------------------------------------------------------


def merchant_account(force_refresh=False):
    if not force_refresh:
        cached = cache.get(MERCHANT_CACHE_KEY)
        if cached:
            return cached
    try:
        client = build_client_from_settings()
        balance = client.get_wallet_balance()
        movements = client.get_wallet_movements(limit=20)
    except PaymentGatewayError as exc:
        raise ServiceUnavailableError(
            f"Impossible de récupérer le compte marchand HR-Skills Pay pour le moment : {exc}",
            code="MERCHANT_ACCOUNT_UNAVAILABLE",
        ) from exc
    data = {"balance": balance, "movements": movements, "fetched_at": timezone.now().isoformat()}
    cache.set(MERCHANT_CACHE_KEY, data, MERCHANT_CACHE_TTL)
    return data


# ---------------------------------------------------------------------------
# Rapprochement financier
# ---------------------------------------------------------------------------


def run_reconciliation(actor, *, period_from, period_to, request=None):
    run = ReconciliationRun.objects.create(period_from=period_from, period_to=period_to, started_by=actor)
    try:
        internal = {
            p.reference: p
            for p in Payment.objects.filter(initiated_at__date__gte=period_from, initiated_at__date__lte=period_to)
        }
        client = build_client_from_settings()
        provider_txns = client.list_transactions(date_from=str(period_from), date_to=str(period_to), limit=100)
        provider_by_ref = {t.get("reference"): t for t in provider_txns if t.get("reference")}

        items = []
        for reference, payment in internal.items():
            provider_txn = provider_by_ref.pop(reference, None)
            if provider_txn is None:
                result = ReconciliationItem.MISSING
                provider_status, received = "", None
            else:
                provider_status = str(provider_txn.get("status", "")).upper()
                received = provider_txn.get("amount")
                if received is not None and int(received) != payment.amount_xaf:
                    result = ReconciliationItem.AMOUNT_MISMATCH
                elif provider_status and provider_status != payment.status:
                    result = ReconciliationItem.STATUS_MISMATCH
                else:
                    result = ReconciliationItem.MATCH
            items.append(ReconciliationItem(
                run=run, internal_reference=reference, provider_reference=payment.provider_reference,
                expected_xaf=payment.amount_xaf, received_xaf=received,
                internal_status=payment.status, provider_status=provider_status, result=result,
            ))

        # Transactions vues chez le prestataire sans paiement interne correspondant.
        for reference, txn in provider_by_ref.items():
            items.append(ReconciliationItem(
                run=run, internal_reference="", provider_reference=reference,
                expected_xaf=None, received_xaf=txn.get("amount"),
                internal_status="", provider_status=str(txn.get("status", "")).upper(),
                result=ReconciliationItem.UNMATCHED_PROVIDER,
            ))

        ReconciliationItem.objects.bulk_create(items)
        run.status = ReconciliationRun.COMPLETED
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "finished_at", "updated_at"])
    except PaymentGatewayError as exc:
        run.status = ReconciliationRun.FAILED
        run.error_message = str(exc)[:255]
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
        raise ServiceUnavailableError(f"Rapprochement échoué : {exc}", code="RECONCILIATION_FAILED") from exc

    record(request=request, actor=actor, action=A.RECONCILIATION_RUN, module=M.FINANCE, resource="reconciliation_run",
           resource_id=run.pk, metadata={"period_from": str(period_from), "period_to": str(period_to), "items": len(items)})
    return run


# ---------------------------------------------------------------------------
# Rapports périodiques
# ---------------------------------------------------------------------------


def report(*, range_key, date_from=None, date_to=None):
    today = timezone.localdate()
    if range_key == "today":
        date_from = date_to = today
    elif range_key == "week":
        date_from, date_to = today - timezone.timedelta(days=today.weekday()), today
    elif range_key == "month":
        date_from, date_to = today.replace(day=1), today
    # "custom" : date_from / date_to fournis par l'appelant

    qs = Payment.objects.filter(initiated_at__date__gte=date_from, initiated_at__date__lte=date_to)
    successful = qs.filter(status=Payment.SUCCESS)
    aggregates = successful.aggregate(volume=Sum("amount_xaf"), fees=Sum("fees_xaf"))
    volume = aggregates["volume"] or 0
    fees = aggregates["fees"] or 0
    counts = qs.aggregate(
        successful=Count("id", filter=Q(status=Payment.SUCCESS)),
        failed=Count("id", filter=Q(status__in=[Payment.FAILED, Payment.CANCELLED, Payment.EXPIRED])),
        pending=Count("id", filter=Q(status__in=[Payment.PENDING, Payment.HOLD])),
    )
    return {
        "range": range_key, "date_from": str(date_from), "date_to": str(date_to),
        "transaction_count": qs.count(), "volume_xaf": volume, "net_amount_xaf": volume - fees,
        "successful_payments": counts["successful"], "failed_payments": counts["failed"], "pending_payments": counts["pending"],
    }
