from django.db import transaction

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record

from .models import Partner


@transaction.atomic
def create_partner(actor, *, request=None, **fields):
    fields.setdefault("order", Partner.objects.count() + 1)
    partner = Partner.objects.create(**fields)
    record(request=request, actor=actor, action=A.PARTNER_CREATED, module=M.PARTNERS,
           resource="partner", resource_id=partner.pk, metadata={"name": partner.name})
    return partner


@transaction.atomic
def update_partner(actor, partner, *, request=None, **fields):
    for key, value in fields.items():
        setattr(partner, key, value)
    partner.save()
    record(request=request, actor=actor, action=A.PARTNER_UPDATED, module=M.PARTNERS,
           resource="partner", resource_id=partner.pk, metadata={"fields": list(fields.keys())})
    return partner


@transaction.atomic
def delete_partner(actor, partner, *, request=None):
    name, pk = partner.name, partner.pk
    partner.delete()
    record(request=request, actor=actor, action=A.PARTNER_DELETED, module=M.PARTNERS,
           resource="partner", resource_id=pk, metadata={"name": name})