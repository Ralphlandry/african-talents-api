from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.settings import api_settings


class AdminJWTAuthentication(JWTAuthentication):
    """JWT + chargement du rôle en une requête ; refuse immédiatement les comptes désactivés."""

    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError:
            raise InvalidToken("Jeton sans identifiant utilisateur.")
        try:
            user = self.user_model.objects.select_related("role").get(**{api_settings.USER_ID_FIELD: user_id})
        except (self.user_model.DoesNotExist, ValueError):
            raise AuthenticationFailed("Utilisateur introuvable.", code="user_not_found")
        if not user.is_active:
            raise AuthenticationFailed("Compte désactivé.", code="user_inactive")
        return user
