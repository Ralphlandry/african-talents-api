from django.db import transaction
from django.utils.text import slugify

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record
from apps.core.exceptions import ConflictError

from .models import Competition, Phase


def _unique_slug(name, exclude_pk=None):
    base = slugify(name)[:170] or "competition"
    slug, n = base, 2
    qs = Competition.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


@transaction.atomic
def create_competition(actor, *, request=None, **fields):
    fields["slug"] = _unique_slug(fields["name"])
    competition = Competition(**fields)
    competition.full_clean()
    competition.save()
    record(request=request, actor=actor, action=A.COMPETITION_UPDATED, module=M.COMPETITION,
           resource="competition", resource_id=competition.pk, metadata={"created": True, "name": competition.name})
    return competition


@transaction.atomic
def update_competition(actor, competition, *, request=None, **fields):
    for key, value in fields.items():
        setattr(competition, key, value)
    competition.full_clean()
    competition.save()
    record(request=request, actor=actor, action=A.COMPETITION_UPDATED, module=M.COMPETITION,
           resource="competition", resource_id=competition.pk, metadata={"fields": list(fields.keys())})
    return competition


@transaction.atomic
def set_status(actor, competition, status, *, request=None):
    if status == Competition.ACTIVE:
        # Une seule compétition "courante" à la fois : les autres perdent ce marqueur (elles ne changent pas de statut).
        Competition.objects.exclude(pk=competition.pk).filter(is_current=True).update(is_current=False)
        competition.is_current = True
    competition.status = status
    competition.save(update_fields=["status", "is_current", "updated_at"])
    action = A.COMPETITION_STARTED if status == Competition.ACTIVE else A.COMPETITION_STOPPED
    record(request=request, actor=actor, action=action, module=M.COMPETITION,
           resource="competition", resource_id=competition.pk, metadata={"status": status})
    return competition


@transaction.atomic
def toggle_votes(actor, competition, open_, *, request=None):
    competition.votes_open = open_
    competition.save(update_fields=["votes_open", "updated_at"])
    record(request=request, actor=actor, action=A.COMPETITION_UPDATED, module=M.COMPETITION,
           resource="competition", resource_id=competition.pk, metadata={"votes_open": open_})
    return competition


@transaction.atomic
def upsert_phase(actor, competition, phase=None, *, request=None, **fields):
    if phase is None:
        fields.setdefault("order", competition.phases.count() + 1)
        phase = Phase(competition=competition, **fields)
        action = A.PHASE_CREATED
    else:
        for key, value in fields.items():
            setattr(phase, key, value)
        action = A.PHASE_UPDATED
    phase.full_clean()
    phase.save()
    record(request=request, actor=actor, action=action, module=M.COMPETITION,
           resource="phase", resource_id=phase.pk, metadata={"name": phase.name, "status": phase.status})
    return phase


@transaction.atomic
def delete_phase(actor, phase, *, request=None):
    if phase.status == Phase.ACTIVE:
        raise ConflictError("Impossible de supprimer une phase en cours. Changez d'abord son statut.", code="PHASE_ACTIVE")
    name, pk = phase.name, phase.pk
    phase.delete()
    record(request=request, actor=actor, action=A.PHASE_DELETED, module=M.COMPETITION,
           resource="phase", resource_id=pk, metadata={"name": name})
