import logging

from apps.core.utils import get_client_ip, get_user_agent

from .constants import AuditResult
from .models import AuditLog

logger = logging.getLogger(__name__)

_SENSITIVE_FRAGMENTS = ("password", "secret", "token", "key", "authorization", "cvv", "card")


def _scrub(value):
    """Retire toute clé sensible des métadonnées avant écriture."""
    if isinstance(value, dict):
        return {
            k: ("***" if any(f in str(k).lower() for f in _SENSITIVE_FRAGMENTS) else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_scrub(v) for v in value]
    return value


def record(
    *,
    action,
    module,
    request=None,
    actor=None,
    actor_email="",
    resource="",
    resource_id="",
    result=AuditResult.SUCCESS,
    metadata=None,
):
    """Enregistre une entrée d'audit. Ne lève jamais d'exception vers l'appelant."""
    try:
        if actor is None and request is not None:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                actor = user
        return AuditLog.objects.create(
            actor=actor,
            actor_email=(actor.email if actor else actor_email) or "",
            actor_name=(actor.full_name if actor else "") or "",
            action=action,
            module=module,
            resource=resource,
            resource_id=str(resource_id) if resource_id else "",
            result=result,
            ip=get_client_ip(request),
            user_agent=get_user_agent(request),
            metadata=_scrub(metadata or {}),
        )
    except Exception:
        logger.exception("Échec d'écriture du journal d'audit (action=%s)", action)
        return None
