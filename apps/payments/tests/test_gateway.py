import hashlib
import hmac

import pytest

from apps.payments.gateway import HRSkillsPayClient, PaymentGatewayError, verify_webhook_signature
from django.core.exceptions import ImproperlyConfigured


class FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}
        self.content = b"1"

    def json(self):
        return self._json


class ScriptedSession:
    """Faux transport HTTP : consomme les réponses scriptées dans l'ordre, sans dépendance externe."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, json=None, params=None, headers=None, timeout=None):
        self.calls.append({"method": method, "url": url, "json": json, "headers": headers})
        if not self.responses:
            raise AssertionError(f"Aucune réponse scriptée restante pour {method} {url}")
        return self.responses.pop(0)


def make_client(session, environment="test", public_suffix="abc"):
    return HRSkillsPayClient(
        public_key=f"hrsk_pk_{environment}_{public_suffix}",
        secret_key=f"hrsk_sk_{environment}_{public_suffix}",
        environment=environment,
        session=session,
    )


def test_key_environment_mismatch_is_rejected():
    with pytest.raises(ImproperlyConfigured):
        HRSkillsPayClient(public_key="hrsk_pk_live_x", secret_key="hrsk_sk_test_y", environment="test", session=ScriptedSession([]))


def test_invalid_environment_value_is_rejected():
    with pytest.raises(ImproperlyConfigured):
        HRSkillsPayClient(public_key="hrsk_pk_prod_x", secret_key="hrsk_sk_prod_x", environment="prod", session=ScriptedSession([]))


@pytest.mark.django_db
def test_payin_fetches_token_then_calls_endpoint(settings):
    session = ScriptedSession([
        FakeResponse(200, {"token": "tok-123", "expires_in": 2700}),
        FakeResponse(200, {"success": True, "message": "Sandbox", "data": {
            "status": "PENDING", "provider_reference": "HRS-1", "fees": 15, "net_amount": 985,
        }}),
    ])
    client = make_client(session, public_suffix="uniq1")
    result = client.create_mobile_money_payin(
        reference="AT-2026-000001", amount_xaf=1000, phone_number="655500001", operator="MTN",
    )
    assert result["status"] == "PENDING"
    assert result["provider_reference"] == "HRS-1"
    assert result["fees_xaf"] == 15
    assert result["net_amount_xaf"] == 985
    assert len(session.calls) == 2
    token_call = session.calls[0]
    assert token_call["method"] == "POST"
    assert token_call["url"].endswith("/sandbox/v1/auth/transaction-token")
    assert token_call["headers"]["Authorization"] == "Bearer hrsk_pk_test_uniq1"
    assert token_call["json"] == {"api_secret": "hrsk_sk_test_uniq1"}
    assert session.calls[1]["headers"]["Authorization"] == "Bearer hrsk_sk_test_uniq1"
    assert session.calls[1]["headers"]["X-Transaction-Token"] == "tok-123"
    assert session.calls[1]["headers"]["Idempotency-Key"] == "AT-2026-000001"
    assert "/sandbox" in session.calls[1]["url"]  # préfixe sandbox appliqué en environnement "test"


@pytest.mark.django_db
def test_token_is_cached_across_calls(settings):
    session = ScriptedSession([
        FakeResponse(200, {"token": "tok-cached", "expires_in": 2700}),
        FakeResponse(200, {"status": "PENDING", "provider_reference": "HRS-1"}),
        FakeResponse(200, {"status": "SUCCESS", "amount": 1000}),
    ])
    client = make_client(session, public_suffix="uniq2")
    client.create_mobile_money_payin(reference="AT-2026-000002", amount_xaf=1000, phone_number="655500001", operator="MTN")
    client.get_payment_status("AT-2026-000002")
    # 1 appel de jeton + 2 appels métier = 3 requêtes au total (pas de second appel de jeton)
    assert len(session.calls) == 3
    assert sum(1 for c in session.calls if "transaction-token" in c["url"]) == 1


@pytest.mark.django_db
def test_error_response_raises_gateway_error(settings):
    session = ScriptedSession([
        FakeResponse(200, {"token": "tok-err", "expires_in": 2700}),
        FakeResponse(409, {"message": "Référence déjà utilisée", "code": "DUPLICATE_REFERENCE"}),
    ])
    client = make_client(session, public_suffix="uniq3")
    with pytest.raises(PaymentGatewayError) as exc_info:
        client.create_mobile_money_payin(reference="AT-2026-000003", amount_xaf=1000, phone_number="655500001", operator="MTN")
    assert exc_info.value.code == "DUPLICATE_REFERENCE"
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_network_error_wrapped_as_gateway_error(settings):
    import requests

    class FailingSession:
        def request(self, *a, **k):
            raise requests.ConnectionError("boom")

    client = make_client(FailingSession(), public_suffix="uniq4")
    with pytest.raises(PaymentGatewayError) as exc_info:
        client._get_transaction_token()
    assert exc_info.value.code == "NETWORK_ERROR"


def test_verify_webhook_signature_valid_and_invalid():
    body = b'{"reference":"AT-2026-000001","status":"SUCCESS"}'
    secret = "whsec_test"
    good_sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_webhook_signature(body, good_sig, secret) is True
    assert verify_webhook_signature(body, "sha256=deadbeef", secret) is False
    assert verify_webhook_signature(body, "", secret) is False
    assert verify_webhook_signature(body, "md5=abcdef", secret) is False
