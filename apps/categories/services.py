from django.db import transaction
from django.utils.text import slugify

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record

from .models import Category


def _unique_slug(name, competition, exclude_pk=None):
    base = slugify(name)[:130] or "categorie"
    slug, n = base, 2
    qs = Category.objects.filter(competition=competition)
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


@transaction.atomic
def create_category(actor, *, request=None, **fields):
    if not fields.get("slug"):
        fields["slug"] = _unique_slug(fields["name"], fields.get("competition"))
    fields.setdefault("order", (Category.objects.filter(competition=fields.get("competition")).count()) + 1)
    category = Category.objects.create(**fields)
    record(request=request, actor=actor, action=A.CATEGORY_CREATED, module=M.CATEGORIES,
           resource="category", resource_id=category.pk, metadata={"name": category.name})
    return category


@transaction.atomic
def update_category(actor, category, *, request=None, **fields):
    for key, value in fields.items():
        setattr(category, key, value)
    category.save()
    record(request=request, actor=actor, action=A.CATEGORY_UPDATED, module=M.CATEGORIES,
           resource="category", resource_id=category.pk, metadata={"fields": list(fields.keys())})
    return category


@transaction.atomic
def delete_category(actor, category, *, request=None):
    name, pk = category.name, category.pk
    category.delete()
    record(request=request, actor=actor, action=A.CATEGORY_DELETED, module=M.CATEGORIES,
           resource="category", resource_id=pk, metadata={"name": name})


@transaction.atomic
def set_status(actor, category, status, *, request=None):
    category.status = status
    category.save(update_fields=["status", "updated_at"])
    record(request=request, actor=actor, action=A.CATEGORY_PUBLISHED, module=M.CATEGORIES,
           resource="category", resource_id=category.pk, metadata={"status": status})
    return category


@transaction.atomic
def reorder(actor, ordered_ids, *, request=None):
    categories = {str(c.pk): c for c in Category.objects.filter(pk__in=ordered_ids)}
    for index, cat_id in enumerate(ordered_ids, start=1):
        cat = categories.get(str(cat_id))
        if cat and cat.order != index:
            cat.order = index
            cat.save(update_fields=["order", "updated_at"])
    record(request=request, actor=actor, action=A.CATEGORY_REORDERED, module=M.CATEGORIES,
           resource="category", metadata={"order": [str(i) for i in ordered_ids]})
