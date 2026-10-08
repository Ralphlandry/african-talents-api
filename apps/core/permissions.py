import logging

from rest_framework.permissions import SAFE_METHODS, BasePermission

logger = logging.getLogger(__name__)


class DenyByDefault(BasePermission):
    """Permission par défaut : refuse. Une vue sans permission déclarée est inaccessible."""

    def has_permission(self, request, view):
        return False


class RBACPermission(BasePermission):
    """
    Contrôle d'accès par rôle. La vue déclare `permission_map` :
      - ViewSet : {action: 'resource.action' | ('a.b', 'c.d')}   (l'une des permissions suffit)
      - APIView : {'GET': 'resource.action', ...}
    Une action absente de la table est REFUSÉE.
    """

    message = "Vous n'avez pas la permission d'effectuer cette action."

    @staticmethod
    def required_permissions(request, view):
        permission_map = getattr(view, "permission_map", None) or {}
        key = getattr(view, "action", None) or request.method
        value = permission_map.get(key)
        if value is None:
            return ()
        return (value,) if isinstance(value, str) else tuple(value)

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated and user.is_active):
            return False
        required = self.required_permissions(request, view)
        if not required:
            return False
        allowed = any(user.has_permission_key(permission) for permission in required)
        if not allowed and request.method not in SAFE_METHODS:
            self._audit_denied(request, view, required)
        return allowed

    @staticmethod
    def _audit_denied(request, view, required):
        try:
            from apps.audit.constants import AuditAction, AuditModule, AuditResult
            from apps.audit.services import record

            record(
                request=request,
                action=AuditAction.PERMISSION_DENIED,
                module=AuditModule.SECURITY,
                resource=view.__class__.__name__,
                result=AuditResult.DENIED,
                metadata={"required": list(required), "method": request.method, "path": request.path},
            )
        except Exception:  # l'audit ne doit jamais casser la requête
            logger.exception("Impossible d'enregistrer le refus de permission")


class IsSuperAdmin(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_super_admin)
