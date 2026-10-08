"""
Client HTTP pour HR-Skills Pay.

IMPORTANT — limite honnête de cette implémentation :
Je n'ai pas eu accès à la documentation officielle interactive (hrskills-pay.com/docs) ni
à un accès réseau pour installer et inspecter le SDK Python officiel `hrpay`. Ce client est
donc écrit contre le CONTRAT HTTP tel que documenté dans les README publics des SDK
officiels (Python/Go/PHP) — endpoints, en-têtes, formats de réponse — et non contre une API
Python de SDK que je ne peux pas vérifier. Les noms de champs de réponse (`status`,
`provider_reference`, `fees`...) sont donc une reconstruction prudente : `_extract` lit
plusieurs noms plausibles pour chaque champ afin de limiter la casse si HR-Skills Pay utilise
une convention légèrement différente, mais un test réel en sandbox (clés `hrsk_*_test_...`)
reste nécessaire avant toute mise en production — voir le rapport d'architecture, §12, pour
le détail des contradictions relevées entre les sources.
"""
import hashlib
import hmac
import logging
import time

import requests
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15  # secondes
TOKEN_CACHE_KEY = "hrskills_pay:transaction_token"
TOKEN_TTL_SECONDS = 40 * 60  # un peu sous les 45 min documentées, par prudence


class PaymentGatewayError(Exception):
    """Erreur de communication avec HR-Skills Pay (réseau, réponse invalide, refus de l'API)."""

    def __init__(self, message, *, code="GATEWAY_ERROR", status_code=None, payload=None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.payload = payload


def _extract(data, *names, default=None):
    for name in names:
        if isinstance(data, dict) and name in data and data[name] is not None:
            return data[name]
    nested_data = data.get("data") if isinstance(data, dict) else None
    if isinstance(nested_data, dict):
        for name in names:
            if name in nested_data and nested_data[name] is not None:
                return nested_data[name]
    return default


class HRSkillsPayClient:
    """
    Client bas niveau. Le transport HTTP (`session`) est injectable pour les tests — voir
    apps/payments/tests/test_gateway.py — sans dépendre d'une bibliothèque de mock réseau.
    """

    def __init__(self, *, public_key, secret_key, environment, base_url=None, session=None, use_sandbox_prefix=None):
        if environment not in ("test", "live"):
            raise ImproperlyConfigured("HRSKILLS_ENVIRONMENT doit valoir 'test' ou 'live'.")
        self._check_key_matches_environment(public_key, "public", environment)
        self._check_key_matches_environment(secret_key, "secret", environment)

        self.public_key = public_key
        self.secret_key = secret_key
        self.environment = environment
        self.base_url = (base_url or "https://api.hrskills-pay.com").rstrip("/")
        self.session = session or requests.Session()
        # Contradiction relevée entre les SDK officiels sur l'existence d'un préfixe
        # /sandbox en environnement de test (cf. rapport §12) — rendu configurable.
        self.use_sandbox_prefix = (
            use_sandbox_prefix if use_sandbox_prefix is not None
            else getattr(settings, "HRSKILLS_USE_SANDBOX_PREFIX", True)
        )

    @staticmethod
    def _check_key_matches_environment(key, kind, environment):
        prefix = f"hrsk_{'pk' if kind == 'public' else 'sk'}_{environment}_"
        if not key.startswith(prefix):
            raise ImproperlyConfigured(
                f"La clé {kind} HR-Skills Pay ne correspond pas à l'environnement déclaré "
                f"({environment!r}) : elle devrait commencer par {prefix!r}."
            )

    # -- authentification (double clé -> transaction token, mis en cache) -------------
    def _get_transaction_token(self):
        cache_key = f"{TOKEN_CACHE_KEY}:{self.environment}:{self.public_key[-8:]}"
        cached = cache.get(cache_key)
        if cached:
            return cached
        response = self._raw_request(
            "POST", "/v1/auth/transaction-token",
            json={"api_secret": self.secret_key},
            headers={"Authorization": f"Bearer {self.public_key}"},
            authenticated=False,
        )
        token = _extract(response, "token", "transaction_token", "access_token")
        if not token:
            raise PaymentGatewayError("Réponse d'authentification HR-Skills Pay invalide (jeton absent).", code="AUTH_FAILED")
        expires_in = _extract(response, "expires_in", default=TOKEN_TTL_SECONDS)
        cache.set(cache_key, token, timeout=max(60, int(expires_in) - 60))
        return token

    def _path(self, path):
        if self.environment == "test" and self.use_sandbox_prefix and not path.startswith("/sandbox"):
            return "/sandbox" + path
        return path

    def _raw_request(self, method, path, *, json=None, params=None, headers=None, authenticated=True):
        url = f"{self.base_url}{self._path(path)}"
        final_headers = {"Content-Type": "application/json", **(headers or {})}
        if authenticated:
            final_headers["Authorization"] = f"Bearer {self.secret_key}"
            final_headers["X-Transaction-Token"] = self._get_transaction_token()

        try:
            response = self.session.request(
                method, url, json=json, params=params, headers=final_headers, timeout=DEFAULT_TIMEOUT
            )
        except requests.RequestException as exc:
            raise PaymentGatewayError(f"Erreur réseau vers HR-Skills Pay : {exc}", code="NETWORK_ERROR") from exc

        try:
            body = response.json() if response.content else {}
        except ValueError:
            body = {}

        if response.status_code == 401 and authenticated:
            # Jeton peut-être expiré entre le cache et l'appel : une seule tentative de rafraîchissement.
            cache.delete(f"{TOKEN_CACHE_KEY}:{self.environment}:{self.public_key[-8:]}")
            final_headers["X-Transaction-Token"] = self._get_transaction_token()
            response = self.session.request(method, url, json=json, params=params, headers=final_headers, timeout=DEFAULT_TIMEOUT)
            try:
                body = response.json() if response.content else {}
            except ValueError:
                body = {}

        if response.status_code >= 400:
            message = _extract(body, "message", "error", default=f"Erreur HR-Skills Pay ({response.status_code}).")
            code = _extract(body, "code", "error_code", default="GATEWAY_ERROR")
            raise PaymentGatewayError(message, code=code, status_code=response.status_code, payload=body)

        return body

    # -- opérations exposées -----------------------------------------------------------
    def create_mobile_money_payin(self, *, reference, amount_xaf, phone_number, operator, description="", metadata=None, country="CM", idempotency_key=None):
        body = self._raw_request(
            "POST", "/api/v1/payin/mobile-money",
            json={
                "reference": reference, "amount": amount_xaf, "currency": "XAF",
                "phone_number": phone_number, "operator": operator, "country": country,
                "description": description, "metadata": metadata or {},
            },
            headers={"Idempotency-Key": idempotency_key or reference},
        )
        return {
            "status": _extract(body, "status", "state", default="PENDING"),
            "provider_reference": _extract(body, "provider_reference", "id", "transaction_id"),
            "fees_xaf": _extract(body, "fees", "fee_amount"),
            "net_amount_xaf": _extract(body, "net_amount", "net"),
            "raw": body,
        }

    def get_payment_status(self, reference):
        body = self._raw_request("GET", f"/v1/payments/{reference}")
        return {
            "status": _extract(body, "status", "state"),
            "amount_xaf": _extract(body, "amount"),
            "currency": _extract(body, "currency"),
            "fees_xaf": _extract(body, "fees", "fee_amount"),
            "net_amount_xaf": _extract(body, "net_amount", "net"),
            "raw": body,
        }

    def list_transactions(self, *, status=None, operator=None, date_from=None, date_to=None, limit=100):
        params = {"limit": min(limit, 100)}
        if status:
            params["status"] = status
        if operator:
            params["operator"] = operator
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        body = self._raw_request("GET", "/v1/transactions", params=params)
        return _extract(body, "data", "results", "transactions", default=body if isinstance(body, list) else [])

    def refund_payment(self, reference):
        body = self._raw_request("POST", f"/v1/payments/{reference}/refund")
        return {"status": _extract(body, "status", "state", default="REFUNDED"), "raw": body}

    def get_wallet_balance(self):
        body = self._raw_request("GET", "/v1/wallet/balance")
        return {
            "available_xaf": _extract(body, "available", "available_balance"),
            "held_xaf": _extract(body, "held", "held_balance"),
            "total_xaf": _extract(body, "total", "total_balance"),
            "currency": _extract(body, "currency", default="XAF"),
            "raw": body,
        }

    def get_wallet_movements(self, *, limit=50):
        body = self._raw_request("GET", "/v1/wallet/movements", params={"limit": limit})
        return _extract(body, "data", "results", "movements", default=body if isinstance(body, list) else [])


def verify_webhook_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    """
    En-tête documenté : `X-Hub-Signature: sha256=<hmac hex>`, calculé sur le corps BRUT.
    Comparaison en temps constant pour éviter les attaques par mesure de timing.
    """
    if not signature_header or "=" not in signature_header:
        return False
    algo, _, signature = signature_header.partition("=")
    if algo.lower() != "sha256":
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def build_client_from_settings():
    """Construit le client à partir des variables d'environnement. Lève ImproperlyConfigured si mal configuré."""
    environment = getattr(settings, "HRSKILLS_ENVIRONMENT", "")
    public_key = getattr(settings, "HRSKILLS_PUBLIC_KEY", "")
    secret_key = getattr(settings, "HRSKILLS_SECRET_KEY", "")
    if not (environment and public_key and secret_key):
        raise ImproperlyConfigured(
            "Configuration HR-Skills Pay incomplète : HRSKILLS_ENVIRONMENT, HRSKILLS_PUBLIC_KEY "
            "et HRSKILLS_SECRET_KEY doivent être définies."
        )
    if environment == "live" and not getattr(settings, "HRSKILLS_ALLOW_LIVE", False):
        raise ImproperlyConfigured(
            "HRSKILLS_ENVIRONMENT=live nécessite aussi HRSKILLS_ALLOW_LIVE=true (garde-fou volontaire "
            "contre un basculement accidentel en production — cf. rapport, §12 et §15)."
        )
    return HRSkillsPayClient(public_key=public_key, secret_key=secret_key, environment=environment)
