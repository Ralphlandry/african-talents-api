from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record

from .models import NewsPost
from .sanitize import sanitize_html


def _unique_slug(title, exclude_pk=None):
    base = slugify(title)[:230] or "article"
    slug, n = base, 2
    qs = NewsPost.objects.all()
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    while qs.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _resolve_status(fields):
    """Un statut explicite gagne ; sinon une date de programmation future implique SCHEDULED."""
    if "status" in fields:
        return fields["status"]
    if fields.get("scheduled_at"):
        return NewsPost.SCHEDULED
    return None


@transaction.atomic
def create_post(actor, *, request=None, **fields):
    if "content_html" in fields:
        fields["content_html"] = sanitize_html(fields["content_html"])
    fields["slug"] = _unique_slug(fields["title"])
    status = _resolve_status(fields) or NewsPost.DRAFT
    fields["status"] = status
    post = NewsPost.objects.create(author=actor, **fields)
    action = A.NEWS_SCHEDULED if status == NewsPost.SCHEDULED else A.NEWS_CREATED
    record(request=request, actor=actor, action=action, module=M.NEWS,
           resource="news_post", resource_id=post.pk, metadata={"title": post.title, "status": status})
    return post


@transaction.atomic
def update_post(actor, post, *, request=None, **fields):
    if "content_html" in fields:
        fields["content_html"] = sanitize_html(fields["content_html"])
    resolved_status = _resolve_status(fields)
    if resolved_status:
        fields["status"] = resolved_status
    for key, value in fields.items():
        setattr(post, key, value)
    post.save()
    record(request=request, actor=actor, action=A.NEWS_UPDATED, module=M.NEWS,
           resource="news_post", resource_id=post.pk, metadata={"fields": list(fields.keys())})
    return post


@transaction.atomic
def delete_post(actor, post, *, request=None):
    title, pk = post.title, post.pk
    post.delete()
    record(request=request, actor=actor, action=A.NEWS_DELETED, module=M.NEWS,
           resource="news_post", resource_id=pk, metadata={"title": title})


@transaction.atomic
def publish_now(actor, post, *, request=None):
    post.status = NewsPost.PUBLISHED
    post.published_at = timezone.now()
    post.scheduled_at = None
    post.save(update_fields=["status", "published_at", "scheduled_at", "updated_at"])
    record(request=request, actor=actor, action=A.NEWS_PUBLISHED, module=M.NEWS,
           resource="news_post", resource_id=post.pk, metadata={"title": post.title})
    return post


@transaction.atomic
def unpublish(actor, post, *, request=None):
    post.status = NewsPost.DRAFT
    post.save(update_fields=["status", "updated_at"])
    record(request=request, actor=actor, action=A.NEWS_UNPUBLISHED, module=M.NEWS,
           resource="news_post", resource_id=post.pk, metadata={"title": post.title})
    return post


@transaction.atomic
def bulk_publish(actor, ids, *, request=None):
    updated = NewsPost.objects.filter(pk__in=ids).update(
        status=NewsPost.PUBLISHED, published_at=timezone.now(), scheduled_at=None
    )
    record(request=request, actor=actor, action=A.NEWS_PUBLISHED, module=M.NEWS,
           resource="news_post", metadata={"bulk": True, "count": updated, "ids": [str(i) for i in ids]})
    return updated


@transaction.atomic
def bulk_delete(actor, ids, *, request=None):
    qs = NewsPost.objects.filter(pk__in=ids)
    count = qs.count()
    for post in qs:
        post.delete()
    record(request=request, actor=actor, action=A.NEWS_DELETED, module=M.NEWS,
           resource="news_post", metadata={"bulk": True, "count": count, "ids": [str(i) for i in ids]})
    return count


def publish_due_scheduled_posts():
    """Appelée par la tâche Celery périodique : publie les articles dont la date programmée est atteinte."""
    due = NewsPost.objects.filter(status=NewsPost.SCHEDULED, scheduled_at__lte=timezone.now())
    count = due.update(status=NewsPost.PUBLISHED, published_at=timezone.now())
    if count:
        record(action=A.NEWS_PUBLISHED, module=M.NEWS, resource="news_post",
               metadata={"auto_scheduled": True, "count": count})
    return count
