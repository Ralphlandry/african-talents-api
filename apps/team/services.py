from django.db import transaction

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record

from .models import TeamMember


@transaction.atomic
def create_member(actor, *, request=None, **fields):
    fields.setdefault("order", TeamMember.objects.filter(type=fields.get("type")).count() + 1)
    member = TeamMember.objects.create(**fields)
    record(request=request, actor=actor, action=A.TEAM_MEMBER_CREATED, module=M.TEAM,
           resource="team_member", resource_id=member.pk, metadata={"name": member.full_name})
    return member


@transaction.atomic
def update_member(actor, member, *, request=None, **fields):
    for key, value in fields.items():
        setattr(member, key, value)
    member.save()
    record(request=request, actor=actor, action=A.TEAM_MEMBER_UPDATED, module=M.TEAM,
           resource="team_member", resource_id=member.pk, metadata={"fields": list(fields.keys())})
    return member


@transaction.atomic
def delete_member(actor, member, *, request=None):
    name, pk = member.full_name, member.pk
    member.delete()
    record(request=request, actor=actor, action=A.TEAM_MEMBER_DELETED, module=M.TEAM,
           resource="team_member", resource_id=pk, metadata={"name": name})
