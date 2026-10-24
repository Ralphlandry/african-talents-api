import hashlib
import hmac
import json

import pytest
from django.utils import timezone

from apps.core.exceptions import ConflictError, ServiceUnavailableError
from apps.payments.gateway import PaymentGatewayError
from apps.payments.models import Payment, PaymentEvent
from apps.voting.models import Vote, VoteOrder


class FakeGatewayClient:
    def __init__(self, payin_result=None, status_result=None, transactions=None,
                 wallet_balance=None, wallet_movements=None, raise_on_payin=None, raise_on_status=None,
                 card_result=None, card_status_result=None):
        self.payin_result = payin_result or {"status": "PENDING", "provider_reference": "HRS-1", "fees_xaf": None, "net_amount_xaf": None}
        self.status_result = status_result
        self.transactions = transactions or []
        self.wallet_balance = wallet_balance or {"available_xaf": 0, "held_xaf": 0, "total_xaf": 0, "currency": "XAF"}
        self.wallet_movements = wallet_movements or []
        self.raise_on_payin = raise_on_payin
        self.raise_on_status = raise_on_status
        self.card_result = card_result or {
            "status": "PENDING", "provider_reference": "CARD-1",
            "checkout_url": "https://pay.enkap.cm/checkout/CARD-1",
        }
        self.card_status_result = card_status_result
        self.refund_calls = []

    def create_mobile_money_payin(self, **kwargs):
        if self.raise_on_payin:
            raise self.raise_on_payin
        self.payin_kwargs = kwargs
        return self.payin_result

    def get_payment_status(self, reference):
        if self.raise_on_status:
            raise self.raise_on_status
        return self.status_result

    def create_card_payment(self, **kwargs):
        self.card_kwargs = kwargs
        return self.card_result

    def get_card_payment_status(self, reference):
        self.card_status_reference = reference
        return self.card_status_result

    def list_transactions(self, **kwargs):
        return self.transactions

    def refund_payment(self, reference):
        self.refund_calls.append(reference)
        return {"status": "REFUNDED"}

    def get_wallet_balance(self):
        return self.wallet_balance

    def get_wallet_movements(self, **kwargs):
        return self.wallet_movements


@pytest.fixture
def order(make_competition, make_category, make_candidate, make_vote_package, make_vote_order):
    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition, quantity=10, price_xaf=1000)
    return make_vote_order(candidate, package)


def sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Initiation
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_initiate_payment_creates_pending_payment(monkeypatch, order):
    from apps.payments import services

    fake = FakeGatewayClient(payin_result={"status": "PENDING", "provider_reference": "HRS-42", "fees_xaf": None, "net_amount_xaf": None})
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    payment = services.initiate_payment(order)
    assert payment.status == Payment.PENDING
    assert payment.provider_reference == "HRS-42"
    assert payment.reference == order.order_number


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("phone", "expected_phone"),
    [
        ("+237655500001", "655500001"),
        ("00237655500001", "655500001"),
        ("237655500001", "655500001"),
        ("655500001", "655500001"),
    ],
)
def test_mobile_money_payin_uses_cameroon_national_number(monkeypatch, order, phone, expected_phone):
    from apps.payments import services

    order.customer_phone = phone
    order.save(update_fields=["customer_phone", "updated_at"])
    fake = FakeGatewayClient()
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    services.initiate_payment(order)

    assert fake.payin_kwargs["phone_number"] == expected_phone


@pytest.mark.django_db
def test_initiate_card_payment_creates_hosted_checkout(monkeypatch, order, settings):
    from apps.payments import services

    settings.HRSKILLS_CARD_ENABLED = True
    settings.HRSKILLS_CARD_RETURN_URL = "https://talents.example/paiement/retour"
    settings.HRSKILLS_PUBLIC_KEY = "hrsk_pk_test_card"
    settings.HRSKILLS_SECRET_KEY = "hrsk_sk_test_card"
    order.operator = "CARD"
    order.customer_phone = ""
    order.save(update_fields=["operator", "customer_phone", "updated_at"])
    fake = FakeGatewayClient()
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    payment = services.initiate_payment(order)

    assert payment.provider == "hrskills_pay_card"
    assert payment.provider_reference == "CARD-1"
    assert payment.checkout_url == "https://pay.enkap.cm/checkout/CARD-1"
    assert fake.card_kwargs["amount_xaf"] == order.amount_xaf
    assert fake.card_kwargs["currency"] == "XAF"
    assert fake.card_kwargs["idempotency_key"] == order.idempotency_key
    assert f"order_number={order.order_number}" in fake.card_kwargs["return_url"]
    assert f"order_number={order.order_number}" in fake.card_kwargs["cancel_url"]


@pytest.mark.django_db
def test_immediate_successful_payin_credits_order(monkeypatch, order):
    from apps.payments import services

    fake = FakeGatewayClient(payin_result={"status": "SUCCESS", "provider_reference": "HRS-PAID"})
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    payment = services.initiate_payment(order)

    order.refresh_from_db()
    assert payment.status == Payment.SUCCESS
    assert payment.provider_reference == "HRS-PAID"
    assert order.status == VoteOrder.PAID
    assert Vote.objects.get(vote_order=order).quantity == order.quantity


@pytest.mark.django_db
def test_initiate_payment_gateway_failure_marks_order_and_payment_failed(monkeypatch, order):
    from apps.payments import services

    fake = FakeGatewayClient(raise_on_payin=PaymentGatewayError("indisponible", code="NETWORK_ERROR"))
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    with pytest.raises(ServiceUnavailableError):
        services.initiate_payment(order)

    order.refresh_from_db()
    payment = Payment.objects.get(vote_order=order)
    assert order.status == VoteOrder.FAILED
    assert payment.status == Payment.FAILED
    assert payment.failure_reason


# ---------------------------------------------------------------------------
# Machine à états
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_illegal_transition_is_rejected(order, make_payment):
    from apps.payments import services

    payment = make_payment(order, status=Payment.FAILED)
    with pytest.raises(ConflictError):
        services.apply_status(payment, Payment.PENDING)


@pytest.mark.django_db
def test_success_transition_credits_exactly_one_vote(order, make_payment):
    from apps.payments import services

    payment = make_payment(order, status=Payment.PENDING)
    services.apply_status(payment, Payment.SUCCESS)

    order.refresh_from_db()
    payment.refresh_from_db()
    assert order.status == VoteOrder.PAID
    assert payment.status == Payment.SUCCESS
    votes = Vote.objects.filter(vote_order=order)
    assert votes.count() == 1
    assert votes.first().quantity == order.quantity


@pytest.mark.django_db
def test_replaying_the_same_status_does_not_duplicate_votes(order, make_payment):
    from apps.payments import services

    payment = make_payment(order, status=Payment.PENDING)
    services.apply_status(payment, Payment.SUCCESS)
    services.apply_status(payment, Payment.SUCCESS)  # rejeu : ne doit rien faire de plus
    assert Vote.objects.filter(vote_order=order).count() == 1


@pytest.mark.django_db
def test_card_status_is_verified_and_capture_credits_votes(monkeypatch, order, make_payment, settings):
    from apps.payments import services

    payment = make_payment(order, status=Payment.PENDING, provider="hrskills_pay_card", provider_reference="CARD-42")
    fake = FakeGatewayClient(card_status_result={
        "status": "CAPTURED", "amount_xaf": order.amount_xaf, "currency": "XAF",
    })
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    result = services.refresh_pending_payment(payment)

    order.refresh_from_db()
    assert result.status == Payment.SUCCESS
    assert order.status == VoteOrder.PAID
    assert fake.card_status_reference == "CARD-42"
    assert Vote.objects.get(vote_order=order).quantity == order.quantity


@pytest.mark.django_db
def test_failed_status_keeps_provider_failure_reason(monkeypatch, order, make_payment):
    from apps.payments import services

    payment = make_payment(order, status=Payment.PENDING, provider_reference="HRS-FAILED")
    fake = FakeGatewayClient(status_result={
        "status": Payment.FAILED,
        "amount_xaf": order.amount_xaf,
        "currency": "XAF",
        "raw": {"data": {"reason": "Solde insuffisant"}},
    })
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    services.refresh_pending_payment(payment)

    payment.refresh_from_db()
    assert payment.status == Payment.FAILED
    assert payment.failure_reason == "Solde insuffisant"


@pytest.mark.django_db
def test_card_webhook_looks_up_provider_reference_and_reverifies(monkeypatch, order, make_payment, settings):
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "card-webhook-secret"
    payment = make_payment(order, status=Payment.PENDING, provider="hrskills_pay_card", provider_reference="CARD-43")
    fake = FakeGatewayClient(card_status_result={
        "status": "CAPTURED", "amount_xaf": order.amount_xaf, "currency": "XAF",
    })
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)
    body = json.dumps({
        "event_id": "card-event-43",
        "reference": "CARD-43",
        "event_type": "card_payment.succeeded",
    }).encode()

    event = services.handle_webhook(body, sign(body, settings.HRSKILLS_WEBHOOK_SECRET))

    payment.refresh_from_db()
    assert event.processed is True
    assert payment.status == Payment.SUCCESS
    assert fake.card_status_reference == "CARD-43"
    assert Vote.objects.get(vote_order=order).quantity == order.quantity


@pytest.mark.django_db
def test_success_can_be_refunded(order, make_payment):
    from apps.payments import services

    paid = make_payment(order, status=Payment.SUCCESS, confirmed_at=timezone.now())
    services.apply_status(paid, Payment.REFUNDED)
    assert paid.status == Payment.REFUNDED


@pytest.mark.django_db
def test_failed_payment_cannot_be_refunded(make_competition, make_category, make_candidate, make_vote_package, make_vote_order, make_payment):
    from apps.payments import services

    # Une commande distincte : un paiement FAILED ne doit jamais pouvoir passer à REFUNDED.
    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition)
    other_order = make_vote_order(candidate, package, idempotency_key="other-order-key")
    failed = make_payment(other_order, status=Payment.FAILED, confirmed_at=timezone.now())

    with pytest.raises(ConflictError):
        services.apply_status(failed, Payment.REFUNDED)


# ---------------------------------------------------------------------------
# Webhook
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_webhook_rejects_invalid_signature(settings, order, make_payment):
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    make_payment(order, status=Payment.PENDING)
    body = json.dumps({"reference": order.order_number, "status": "SUCCESS", "event_type": "payment.succeeded"}).encode()

    from apps.core.exceptions import DomainError

    with pytest.raises(DomainError) as exc_info:
        services.handle_webhook(body, "sha256=not-the-right-signature")
    assert exc_info.value.error_code == "INVALID_SIGNATURE"
    assert PaymentEvent.objects.filter(signature_valid=False).count() == 1
    order.refresh_from_db()
    assert order.status == VoteOrder.PENDING  # rien n'a bougé


@pytest.mark.django_db
def test_webhook_with_valid_signature_reverifies_and_credits(settings, monkeypatch, order, make_payment):
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    payment = make_payment(order, status=Payment.PENDING)
    fake = FakeGatewayClient(status_result={"status": "SUCCESS", "amount_xaf": order.amount_xaf, "fees_xaf": 20, "net_amount_xaf": order.amount_xaf - 20})
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    body = json.dumps({"reference": order.order_number, "status": "SUCCESS", "event_type": "payment.succeeded"}).encode()
    services.handle_webhook(body, sign(body, "whsec_test"))

    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == Payment.SUCCESS and payment.fees_xaf == 20
    assert order.status == VoteOrder.PAID
    assert Vote.objects.filter(vote_order=order).count() == 1


@pytest.mark.django_db
def test_webhook_amount_mismatch_does_not_credit(settings, monkeypatch, order, make_payment):
    """Le webhook lui-même ne suffit jamais : le montant revérifié doit correspondre."""
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    make_payment(order, status=Payment.PENDING)
    fake = FakeGatewayClient(status_result={"status": "SUCCESS", "amount_xaf": order.amount_xaf + 500})
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    body = json.dumps({"reference": order.order_number, "status": "SUCCESS", "event_type": "payment.succeeded"}).encode()
    services.handle_webhook(body, sign(body, "whsec_test"))

    order.refresh_from_db()
    assert order.status == VoteOrder.PENDING
    assert Vote.objects.filter(vote_order=order).count() == 0


@pytest.mark.django_db
def test_webhook_same_event_is_not_reprocessed(settings, monkeypatch, order, make_payment):
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    make_payment(order, status=Payment.PENDING)
    fake = FakeGatewayClient(status_result={"status": "SUCCESS", "amount_xaf": order.amount_xaf})
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    body = json.dumps({"reference": order.order_number, "status": "SUCCESS", "event_type": "payment.succeeded"}).encode()
    signature = sign(body, "whsec_test")
    services.handle_webhook(body, signature)
    services.handle_webhook(body, signature)  # rejeu exact du même appel webhook

    assert Vote.objects.filter(vote_order=order).count() == 1
    assert PaymentEvent.objects.count() == 1


@pytest.mark.django_db
def test_webhook_for_unknown_reference_is_logged_without_error(settings):
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    body = json.dumps({"reference": "AT-2026-999999", "status": "SUCCESS", "event_type": "payment.succeeded"}).encode()
    event = services.handle_webhook(body, sign(body, "whsec_test"))
    assert event.payment is None
    assert event.processed is True  # traité "avec succès" : on a juste constaté qu'il n'y a rien à faire


@pytest.mark.django_db
def test_terminal_payment_ignores_late_webhook(settings, monkeypatch, order, make_payment):
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    payment = make_payment(order, status=Payment.FAILED, confirmed_at=timezone.now())
    fake = FakeGatewayClient(status_result={"status": "SUCCESS", "amount_xaf": order.amount_xaf})
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    body = json.dumps({"reference": order.order_number, "status": "SUCCESS", "event_type": "payment.succeeded"}).encode()
    services.handle_webhook(body, sign(body, "whsec_test"))

    payment.refresh_from_db()
    assert payment.status == Payment.FAILED  # un paiement déjà terminé ne repart jamais


# ---------------------------------------------------------------------------
# Filet de sécurité (expiration) et remboursement
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_expire_stale_pending_payments(order, make_payment):
    from apps.payments import services

    payment = make_payment(order, status=Payment.PENDING)
    Payment.objects.filter(pk=payment.pk).update(initiated_at=timezone.now() - timezone.timedelta(minutes=30))

    count = services.expire_stale_pending_payments()
    assert count == 1
    payment.refresh_from_db()
    order.refresh_from_db()
    assert payment.status == Payment.EXPIRED
    assert order.status == VoteOrder.EXPIRED


@pytest.mark.django_db
def test_recent_pending_payment_is_not_expired(order, make_payment):
    from apps.payments import services

    make_payment(order, status=Payment.PENDING)
    assert services.expire_stale_pending_payments() == 0


@pytest.mark.django_db
def test_refund_only_allowed_on_successful_payment(order, make_payment, super_admin, monkeypatch):
    from apps.payments import services

    pending = make_payment(order, status=Payment.PENDING)
    with pytest.raises(ConflictError):
        services.refund_payment(super_admin, pending)


# ---------------------------------------------------------------------------
# Endpoint HTTP réel (pas seulement la fonction service) — vérifie le câblage des URLs
# et la lecture du corps brut à travers la pile DRF.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_webhook_endpoint_end_to_end_success(settings, monkeypatch, order, make_payment, api):
    from apps.payments import services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    make_payment(order, status=Payment.PENDING)
    fake = FakeGatewayClient(status_result={"status": "SUCCESS", "amount_xaf": order.amount_xaf})
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    body = json.dumps({"reference": order.order_number, "status": "SUCCESS", "event_type": "payment.succeeded"})
    signature = sign(body.encode(), "whsec_test")
    response = api.post(
        "/api/v1/payments/webhooks/hrskills/", data=body, content_type="application/json",
        HTTP_X_HUB_SIGNATURE=signature,
    )
    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == VoteOrder.PAID


@pytest.mark.django_db
def test_webhook_endpoint_end_to_end_invalid_signature(settings, order, make_payment, api):
    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_test"
    make_payment(order, status=Payment.PENDING)
    body = json.dumps({"reference": order.order_number, "status": "SUCCESS", "event_type": "payment.succeeded"})
    response = api.post(
        "/api/v1/payments/webhooks/hrskills/", data=body, content_type="application/json",
        HTTP_X_HUB_SIGNATURE="sha256=wrong",
    )
    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == VoteOrder.PENDING


@pytest.mark.django_db
def test_refund_success_calls_gateway_and_updates_status(order, make_payment, super_admin, monkeypatch):
    from apps.payments import services

    paid = make_payment(order, status=Payment.SUCCESS, confirmed_at=timezone.now())
    fake = FakeGatewayClient()
    monkeypatch.setattr(services, "build_client_from_settings", lambda: fake)

    services.refund_payment(super_admin, paid)
    paid.refresh_from_db()
    assert paid.status == Payment.REFUNDED
    assert fake.refund_calls == [paid.reference]
