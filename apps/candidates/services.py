from django.db import transaction
from django.utils.text import slugify

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record

from .models import Candidate


@transaction.atomic
def create_candidate(actor, *, request=None, gallery=None, **fields):
    fields.setdefault("slug", slugify(f"{fields['first_name']}-{fields['last_name']}-{fields['code']}")[:220])
    candidate = Candidate.objects.create(**fields)
    if gallery is not None:
        candidate.gallery.set(gallery)
    record(request=request, actor=actor, action=A.CANDIDATE_CREATED, module=M.CANDIDATES,
           resource="candidate", resource_id=candidate.pk, metadata={"code": candidate.code})
    return candidate


@transaction.atomic
def update_candidate(actor, candidate, *, request=None, gallery=None, **fields):
    for key, value in fields.items():
        setattr(candidate, key, value)
    candidate.save()
    if gallery is not None:
        candidate.gallery.set(gallery)
    record(request=request, actor=actor, action=A.CANDIDATE_UPDATED, module=M.CANDIDATES,
           resource="candidate", resource_id=candidate.pk, metadata={"fields": list(fields.keys())})
    return candidate


@transaction.atomic
def delete_candidate(actor, candidate, *, request=None):
    code, pk = candidate.code, candidate.pk
    candidate.delete()
    record(request=request, actor=actor, action=A.CANDIDATE_DELETED, module=M.CANDIDATES,
           resource="candidate", resource_id=pk, metadata={"code": code})


@transaction.atomic
def publish(actor, candidate, *, request=None):
    candidate.status = Candidate.PUBLISHED
    candidate.save(update_fields=["status", "updated_at"])
    record(request=request, actor=actor, action=A.CANDIDATE_PUBLISHED, module=M.CANDIDATES,
           resource="candidate", resource_id=candidate.pk, metadata={"code": candidate.code})
    return candidate


@transaction.atomic
def set_active(actor, candidate, active, *, request=None):
    candidate.is_active = active
    candidate.save(update_fields=["is_active", "updated_at"])
    record(request=request, actor=actor, action=A.CANDIDATE_STATUS_CHANGED, module=M.CANDIDATES,
           resource="candidate", resource_id=candidate.pk, metadata={"is_active": active})
    return candidate


@transaction.atomic
def bulk_publish(actor, ids, *, request=None):
    updated = Candidate.objects.filter(pk__in=ids).update(status=Candidate.PUBLISHED)
    record(request=request, actor=actor, action=A.CANDIDATE_PUBLISHED, module=M.CANDIDATES,
           resource="candidate", metadata={"bulk": True, "count": updated, "ids": [str(i) for i in ids]})
    return updated


@transaction.atomic
def bulk_set_active(actor, ids, active, *, request=None):
    updated = Candidate.objects.filter(pk__in=ids).update(is_active=active)
    record(request=request, actor=actor, action=A.CANDIDATE_STATUS_CHANGED, module=M.CANDIDATES,
           resource="candidate", metadata={"bulk": True, "count": updated, "is_active": active, "ids": [str(i) for i in ids]})
    return updated


@transaction.atomic
def bulk_delete(actor, ids, *, request=None):
    qs = Candidate.objects.filter(pk__in=ids)
    count = qs.count()
    for candidate in qs:
        candidate.delete()
    record(request=request, actor=actor, action=A.CANDIDATE_DELETED, module=M.CANDIDATES,
           resource="candidate", metadata={"bulk": True, "count": count, "ids": [str(i) for i in ids]})
    return count
