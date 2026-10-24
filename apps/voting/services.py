from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record
from apps.candidates.models import Candidate
from apps.core.exceptions import ConflictError, UnprocessableError

from .models import Vote, VoteOrder, VotePackage

HISTORICAL_VOTE_IMPORT_REASON = "Import des votes de l’ancien site"

# ---------------------------------------------------------------------------
# Forfaits de vote (définis par l'admin — décision B : pas de prix unique codé en dur)
# ---------------------------------------------------------------------------


@transaction.atomic
def create_package(actor, *, request=None, **fields):
    fields.setdefault("order", VotePackage.objects.filter(competition=fields.get("competition")).count() + 1)
    package = VotePackage.objects.create(**fields)
    record(request=request, actor=actor, action=A.VOTE_PACKAGE_CREATED, module=M.VOTES,
           resource="vote_package", resource_id=package.pk,
           metadata={"label": package.label, "quantity": package.quantity, "price_xaf": package.price_xaf})
    return package


@transaction.atomic
def update_package(actor, package, *, request=None, **fields):
    for key, value in fields.items():
        setattr(package, key, value)
    package.save()
    record(request=request, actor=actor, action=A.VOTE_PACKAGE_UPDATED, module=M.VOTES,
           resource="vote_package", resource_id=package.pk, metadata={"fields": list(fields.keys())})
    return package


@transaction.atomic
def delete_package(actor, package, *, request=None):
    if package.orders.exists():
        raise ConflictError(
            "Ce forfait a déjà été utilisé dans des commandes et ne peut pas être supprimé. Désactivez-le plutôt.",
            code="PACKAGE_IN_USE",
        )
    label, pk = package.label, package.pk
    package.delete()
    record(request=request, actor=actor, action=A.VOTE_PACKAGE_DELETED, module=M.VOTES,
           resource="vote_package", resource_id=pk, metadata={"label": label})


# ---------------------------------------------------------------------------
# Commande de vote (création de l'ordre ; l'initiation du paiement est faite par
# apps.payments, appelé par la vue publique juste après — cf. apps/publicapi/views.py)
# ---------------------------------------------------------------------------


@transaction.atomic
def create_order(*, candidate, vote_package, phone, operator, idempotency_key, request=None):
    existing = VoteOrder.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False  # rejeu du même clic : on renvoie la commande déjà créée, sans doublon

    competition = candidate.competition
    if not competition.is_current or competition.status != competition.ACTIVE:
        raise UnprocessableError("La compétition n'est pas active.", code="COMPETITION_NOT_ACTIVE")
    if not competition.votes_open:
        raise UnprocessableError("Les votes sont actuellement fermés.", code="VOTES_CLOSED")
    if vote_package.competition_id != competition.id:
        raise UnprocessableError("Ce forfait n'appartient pas à la compétition de ce candidat.", code="PACKAGE_MISMATCH")
    if not vote_package.is_active:
        raise UnprocessableError("Ce forfait n'est plus disponible.", code="PACKAGE_INACTIVE")

    active_phase = next((p for p in competition.phases.all() if p.status == competition.phases.model.ACTIVE), None)

    order = VoteOrder.objects.create(
        candidate=candidate, vote_package=vote_package, phase=active_phase,
        quantity=vote_package.quantity, amount_xaf=vote_package.price_xaf,
        customer_phone=phone, operator=operator, idempotency_key=idempotency_key,
    )
    record(request=request, action=A.VOTE_ORDER_CREATED, module=M.VOTES, resource="vote_order",
           resource_id=order.pk, metadata={"order_number": order.order_number, "candidate": candidate.code,
                                            "amount_xaf": order.amount_xaf})
    return order, True


@transaction.atomic
def credit_paid_order(order):
    """
    Crédite les votes d'une commande payée. Appelée UNIQUEMENT depuis la confirmation
    fiable d'un paiement (webhook re-vérifié), jamais depuis la simple création de la
    commande. La contrainte OneToOne sur Vote.vote_order empêche tout double crédit.
    """
    if hasattr(order, "vote"):
        return order.vote  # déjà crédité (rejeu d'événement) — idempotent
    vote = Vote.objects.create(
        candidate=order.candidate, phase=order.phase, quantity=order.quantity,
        source=Vote.PAID, vote_order=order,
    )
    return vote


# ---------------------------------------------------------------------------
# Ajustement manuel (admin, avec motif obligatoire et traçabilité complète)
# ---------------------------------------------------------------------------


@transaction.atomic
def adjust_votes(actor, *, candidate, phase=None, delta, reason, request=None):
    if reason == HISTORICAL_VOTE_IMPORT_REASON:
        Candidate.objects.select_for_update().get(pk=candidate.pk)
        if Vote.objects.filter(
            candidate=candidate,
            source=Vote.MANUAL_ADJUSTMENT,
            reason=HISTORICAL_VOTE_IMPORT_REASON,
        ).exists():
            raise ConflictError(
                "Les votes de l’ancien site ont déjà été importés pour ce candidat.",
                code="HISTORICAL_VOTES_ALREADY_IMPORTED",
            )

    vote = Vote.objects.create(
        candidate=candidate, phase=phase, quantity=delta, source=Vote.MANUAL_ADJUSTMENT,
        created_by=actor, reason=reason,
    )
    record(request=request, actor=actor, action=A.VOTE_ADJUSTED, module=M.VOTES,
           resource="vote", resource_id=vote.pk,
           metadata={"candidate": candidate.code, "delta": delta, "reason": reason})
    return vote


# ---------------------------------------------------------------------------
# Agrégation / classement (seule source de vérité : la somme du grand livre Vote)
# ---------------------------------------------------------------------------


def annotate_votes_total(queryset, *, phase=None, cumulative=True):
    """
    Ajoute `votes_total_annotated` à un queryset de Candidate.
    cumulative=True : toutes les phases confondues. phase=<Phase> : uniquement cette phase.
    """
    from django.db.models import Q

    vote_filter = Q()
    if not cumulative and phase is not None:
        vote_filter &= Q(votes__phase=phase)
    return queryset.annotate(votes_total_annotated=Sum("votes__quantity", filter=vote_filter, default=0))


def ranked_candidates(competition, *, category=None, phase=None, cumulative=True):
    from apps.candidates.models import Candidate

    qs = Candidate.objects.filter(competition=competition, status=Candidate.PUBLISHED, is_active=True)
    if category is not None:
        qs = qs.filter(category=category)
    qs = annotate_votes_total(qs, phase=phase, cumulative=cumulative)
    return qs.order_by("-votes_total_annotated", "code")


def rank_of(candidate, *, phase=None, cumulative=True):
    """Position du candidat dans le classement de sa propre catégorie."""
    qs = ranked_candidates(candidate.competition, category=candidate.category, phase=phase, cumulative=cumulative)
    for index, current in enumerate(qs, start=1):
        if current.id == candidate.id:
            return index
    return None


def votes_by_category(competition, *, phase=None, cumulative=True):
    from apps.categories.models import Category

    results = []
    for category in Category.objects.filter(competition=competition, status=Category.PUBLISHED):
        qs = annotate_votes_total(
            category.candidates.filter(status="published", is_active=True), phase=phase, cumulative=cumulative
        )
        total = sum(c.votes_total_annotated or 0 for c in qs)
        results.append({"category_id": category.id, "name": category.name, "total": total})
    return results


def votes_series(competition, *, days=14):
    """Série journalière (votes PAID uniquement) pour le graphique du tableau de bord admin."""
    from django.db.models.functions import TruncDate

    since = timezone.now() - timezone.timedelta(days=days)
    rows = (
        Vote.objects.filter(candidate__competition=competition, source=Vote.PAID, created_at__gte=since)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(count=Sum("quantity"))
        .order_by("day")
    )
    return [{"date": row["day"].isoformat(), "count": row["count"] or 0} for row in rows]
