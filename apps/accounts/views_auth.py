from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.constants import AuditResult as R
from apps.audit.services import record
from apps.core.exceptions import (
    AccountDisabledError,
    AccountLockedError,
    DomainError,
    InvalidCredentialsError,
)
from apps.core.throttles import LoginRateThrottle, PasswordResetRateThrottle, RefreshRateThrottle

from . import services
from .models import User
from .serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
)


def set_refresh_cookie(response, token):
    response.set_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        str(token),
        max_age=int(settings.JWT_REFRESH_LIFETIME.total_seconds()),
        httponly=True,
        secure=settings.AUTH_REFRESH_COOKIE_SECURE,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response):
    response.delete_cookie(
        settings.AUTH_REFRESH_COOKIE_NAME,
        path=settings.AUTH_REFRESH_COOKIE_PATH,
        samesite=settings.AUTH_REFRESH_COOKIE_SAMESITE,
    )


def _extract_refresh(request):
    """Refresh token depuis le cookie HttpOnly (ou, pour les clients non-navigateur, le corps JSON)."""
    raw = request.COOKIES.get(settings.AUTH_REFRESH_COOKIE_NAME)
    if not raw and hasattr(request.data, "get"):
        raw = request.data.get("refresh")
    return raw if isinstance(raw, str) and raw else None


def session_payload(user, refresh):
    """Corps de réponse : le refresh token n'est JAMAIS renvoyé dans le JSON (cookie HttpOnly uniquement)."""
    return {
        "access": str(refresh.access_token),
        "expires_in": int(settings.JWT_ACCESS_LIFETIME.total_seconds()),
        "must_change_password": user.must_change_password,
        "user": MeSerializer(user).data,
    }


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginRateThrottle]

    @extend_schema(request=LoginSerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        password = serializer.validated_data["password"]

        user = User.objects.select_related("role").filter(email__iexact=email).first()

        if user is None:
            make_password(password)  # égalise le temps de réponse (pas d'énumération de comptes)
            self._failed(request, email, None)
            raise InvalidCredentialsError()

        if user.is_locked:
            self._failed(request, email, user, reason="locked")
            raise AccountLockedError()

        if not user.check_password(password):
            user.register_failed_login()
            self._failed(request, email, user, reason="bad_password")
            raise InvalidCredentialsError()

        if not user.is_active:
            self._failed(request, email, user, reason="inactive")
            raise AccountDisabledError()

        user.register_successful_login()
        refresh = RefreshToken.for_user(user)
        record(request=request, actor=user, action=A.ADMIN_LOGIN, module=M.AUTH, resource="user", resource_id=user.pk)
        response = Response(session_payload(user, refresh))
        set_refresh_cookie(response, refresh)
        return response

    @staticmethod
    def _failed(request, email, user, reason="unknown_user"):
        record(request=request, actor=None, actor_email=email, action=A.ADMIN_LOGIN_FAILED, module=M.AUTH,
               resource="user", resource_id=user.pk if user else "", result=R.FAILURE, metadata={"reason": reason})


class RefreshView(APIView):
    """Renouvelle la session à partir du cookie HttpOnly (rotation + liste noire de l'ancien jeton)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RefreshRateThrottle]

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        raw = _extract_refresh(request)
        if not raw:
            raise DomainError("Session expirée. Veuillez vous reconnecter.", code="TOKEN_MISSING")
        try:
            old = RefreshToken(raw)  # vérifie signature, expiration et liste noire
            user = User.objects.select_related("role").get(pk=old["user_id"])
        except (TokenError, User.DoesNotExist, KeyError, ValueError):
            response = Response({"success": False, "message": "Session invalide ou expirée.", "code": "TOKEN_INVALID"},
                                status=status.HTTP_401_UNAUTHORIZED)
            clear_refresh_cookie(response)
            return response
        if not user.is_active:
            old.blacklist()
            response = Response({"success": False, "message": "Ce compte est désactivé.", "code": "ACCOUNT_DISABLED"},
                                status=status.HTTP_401_UNAUTHORIZED)
            clear_refresh_cookie(response)
            return response
        new = RefreshToken.for_user(user)
        old.blacklist()
        response = Response(session_payload(user, new))
        set_refresh_cookie(response, new)
        return response


class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(request=None, responses={204: None}, auth=[])
    def post(self, request):
        raw = _extract_refresh(request)
        user = None
        if raw:
            try:
                token = RefreshToken(raw)
                user = User.objects.filter(pk=token["user_id"]).first()
                token.blacklist()
            except (TokenError, KeyError, ValueError):
                pass
        if user:
            record(request=request, actor=user, action=A.ADMIN_LOGOUT, module=M.AUTH, resource="user", resource_id=user.pk)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer)
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.must_change_password = False
        user.save(update_fields=["password", "must_change_password", "updated_at"])
        services.revoke_all_sessions(user)
        record(request=request, actor=user, action=A.PASSWORD_CHANGED, module=M.AUTH, resource="user", resource_id=user.pk)
        refresh = RefreshToken.for_user(user)  # la session courante continue, les autres sont révoquées
        response = Response(session_payload(user, refresh))
        set_refresh_cookie(response, refresh)
        return response


class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(request=PasswordResetRequestSerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            query = urlencode({"uid": uid, "token": token})
            reset_url = f"{settings.ADMIN_FRONTEND_URL}/reset-password?{query}"
            send_mail(
                "Réinitialisation de votre mot de passe African Talents",
                (
                    f"Bonjour {user.full_name},\n\n"
                    "Une demande de réinitialisation du mot de passe de votre compte administrateur "
                    "African Talents a été effectuée.\n\n"
                    f"Pour choisir un nouveau mot de passe, ouvrez ce lien :\n{reset_url}\n\n"
                    "Ce lien est valable pendant une durée limitée et ne peut être utilisé qu'une fois. "
                    "Si vous n'êtes pas à l'origine de cette demande, ignorez cet e-mail."
                ),
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )

        return Response({
            "message": "Si cette adresse correspond à un compte actif, un lien de réinitialisation va être envoyé.",
        })


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetRateThrottle]

    @extend_schema(request=PasswordResetConfirmSerializer, responses=OpenApiTypes.OBJECT, auth=[])
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        with transaction.atomic():
            user.set_password(serializer.validated_data["new_password"])
            user.must_change_password = False
            user.failed_login_count = 0
            user.locked_until = None
            user.save(update_fields=[
                "password", "must_change_password", "failed_login_count", "locked_until", "updated_at",
            ])
            services.revoke_all_sessions(user)

        record(
            request=request,
            actor=user,
            action=A.ADMIN_PASSWORD_RESET,
            module=M.AUTH,
            resource="user",
            resource_id=user.pk,
        )
        return Response({"message": "Votre mot de passe a été réinitialisé. Vous pouvez vous connecter."})
