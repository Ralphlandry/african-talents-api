"""
Format d'erreur unique de l'API :
{"success": false, "message": "...", "code": "PERMISSION_DENIED", "errors": {...}}
"""
import logging

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import ProtectedError
from django.http import Http404
from rest_framework import exceptions as drf_exc
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger(__name__)


class DomainError(drf_exc.APIException):
    """Erreur métier avec un code stable exploitable par les frontends."""

    status_code = 400
    default_detail = "Requête invalide."
    error_code = "DOMAIN_ERROR"

    def __init__(self, detail=None, code=None):
        if code:
            self.error_code = code
        super().__init__(detail=detail, code=(code or self.error_code).lower())


class ForbiddenError(DomainError):
    status_code = 403
    default_detail = "Action interdite."
    error_code = "FORBIDDEN"


class ConflictError(DomainError):
    status_code = 409
    default_detail = "Conflit avec l'état actuel de la ressource."
    error_code = "CONFLICT"


class UnprocessableError(DomainError):
    status_code = 422
    default_detail = "Les données envoyées sont invalides."
    error_code = "UNPROCESSABLE"


class InvalidCredentialsError(DomainError):
    status_code = 401
    default_detail = "Identifiants invalides."
    error_code = "INVALID_CREDENTIALS"


class AccountLockedError(DomainError):
    status_code = 429
    default_detail = "Compte temporairement verrouillé. Réessayez plus tard."
    error_code = "ACCOUNT_LOCKED"


class AccountDisabledError(DomainError):
    status_code = 403
    default_detail = "Ce compte est désactivé."
    error_code = "ACCOUNT_DISABLED"


class ServiceUnavailableError(DomainError):
    status_code = 503
    default_detail = "Service temporairement indisponible."
    error_code = "SERVICE_UNAVAILABLE"


def _plain(detail):
    if isinstance(detail, dict):
        return {key: _plain(value) for key, value in detail.items()}
    if isinstance(detail, (list, tuple)):
        return [_plain(value) for value in detail]
    return str(detail)


def _describe(exc):
    code = getattr(exc, "error_code", None)
    if isinstance(exc, drf_exc.ValidationError):
        return "VALIDATION_ERROR", "Les données envoyées sont invalides.", _plain(exc.detail)
    if code:
        return code, str(exc.detail), None
    if isinstance(exc, drf_exc.NotAuthenticated):
        return "NOT_AUTHENTICATED", "Authentification requise.", None
    if isinstance(exc, drf_exc.AuthenticationFailed):
        return "AUTHENTICATION_FAILED", "Session invalide ou expirée. Veuillez vous reconnecter.", None
    if isinstance(exc, drf_exc.PermissionDenied):
        return "PERMISSION_DENIED", "Vous n'avez pas la permission d'effectuer cette action.", None
    if isinstance(exc, drf_exc.NotFound):
        return "NOT_FOUND", "Ressource introuvable.", None
    if isinstance(exc, drf_exc.Throttled):
        return "RATE_LIMITED", "Trop de requêtes. Réessayez dans quelques instants.", None
    if isinstance(exc, drf_exc.MethodNotAllowed):
        return "METHOD_NOT_ALLOWED", "Méthode non autorisée.", None
    if isinstance(exc, drf_exc.ParseError):
        return "BAD_REQUEST", "Requête mal formée.", None
    return "ERROR", str(exc.detail) if not isinstance(exc.detail, (dict, list)) else "Erreur.", None


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = drf_exc.NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = drf_exc.PermissionDenied()
    elif isinstance(exc, ProtectedError):
        exc = ConflictError("Cette ressource est utilisée ailleurs et ne peut pas être supprimée.", code="PROTECTED")
    elif isinstance(exc, DjangoValidationError):
        exc = drf_exc.ValidationError(detail=exc.message_dict if hasattr(exc, "error_dict") else exc.messages)

    response = drf_exception_handler(exc, context)
    if response is None:
        # Erreur inattendue : détail journalisé côté serveur, jamais exposé au client.
        logger.exception("Erreur non gérée", exc_info=exc)
        set_rollback()
        from rest_framework.response import Response

        return Response(
            {"success": False, "message": "Une erreur interne est survenue.", "code": "INTERNAL_ERROR"},
            status=500,
        )

    code, message, errors = _describe(exc)
    payload = {"success": False, "message": message, "code": code}
    if errors:
        payload["errors"] = errors
    if isinstance(exc, drf_exc.Throttled) and exc.wait is not None:
        payload["retry_after"] = int(exc.wait)
    response.data = payload
    if isinstance(exc, drf_exc.ValidationError):
        response.status_code = 422
    return response
