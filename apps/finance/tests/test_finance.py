import pytest
from django.utils import timezone

from apps.payments.gateway import PaymentGatewayError
from apps.payments.models import Payment

OVERVIEW = "/api/v1/finance/overview/"
MERCHANT = "/api/v1/finance/merchant-account/"
RECONCILE_RUN = "/api/v1/finance/reconciliation/run/"
REPORTS = "/api/v1/finance/reports/"


class FakeFinanceClient:
    def __init__(self, balance=None, movements=None, transactions=None, raise_error=None):
        self.balance = balance or {"available_xaf": 500000, "held_xaf": 20000, "total_xaf": 520000, "currency": "XAF"}
        self.movements = movements or []
        self.transactions = transactions or []
        self.raise_error = raise_error

    def get_wallet_balance(self):
        if self.raise_error:
            raise self.raise_error
        return self.balance

    def get_wallet_movements(self, **kwargs):
        return self.movements

    def list_transactions(self, **kwargs):
        if self.raise_error:
            raise self.raise_error
        return self.transactions


@pytest.fixture
def paid_payment(make_competition, make_category, make_candidate, make_vote_package, make_vote_order, make_payment):
    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition, quantity=10, price_xaf=1000)
    order = make_vote_order(candidate, package)
    payment = make_payment(order, status=Payment.SUCCESS, fees_xaf=20, confirmed_at=timezone.now())
    return payment


@pytest.mark.django_db
def test_overview_aggregates_only_successful_payments(auth_client, make_role, make_user, paid_payment):
    # paid_payment vient du forfait "10 votes pour 1000 FCFA" (prix forfaitaire, pas prix x quantité).
    user = make_user("f@example.com", make_role("Finance", ["payments.statistics"]))
    response = auth_client(user).get(OVERVIEW)
    assert response.status_code == 200
    body = response.json()
    assert body["total_collected_xaf"] == 1000
    assert body["net_amount_xaf"] == 980  # 1000 - 20 de frais
    assert body["successful_payments"] == 1


@pytest.mark.django_db
def test_merchant_account_requires_permission(auth_client, make_role, make_user):
    nobody = make_user("n@example.com", make_role("Rien", []))
    assert auth_client(nobody).get(MERCHANT).status_code == 403


@pytest.mark.django_db
def test_merchant_account_returns_gateway_data(auth_client, make_role, make_user, monkeypatch):
    from apps.finance import services

    monkeypatch.setattr(services, "build_client_from_settings", lambda: FakeFinanceClient())
    user = make_user("f@example.com", make_role("Finance", ["merchant.view"]))
    response = auth_client(user).get(MERCHANT)
    assert response.status_code == 200
    assert response.json()["balance"]["available_xaf"] == 500000


@pytest.mark.django_db
def test_merchant_account_unavailable_returns_clean_error(auth_client, make_role, make_user, monkeypatch):
    from apps.finance import services

    monkeypatch.setattr(services, "build_client_from_settings", lambda: FakeFinanceClient(raise_error=PaymentGatewayError("panne")))
    user = make_user("f@example.com", make_role("Finance", ["merchant.view"]))
    response = auth_client(user).get(MERCHANT)
    assert response.status_code == 503
    assert response.json()["code"] == "MERCHANT_ACCOUNT_UNAVAILABLE"


@pytest.mark.django_db
def test_reconciliation_detects_match_missing_and_amount_mismatch(auth_client, make_role, make_user, monkeypatch, paid_payment):
    from apps.finance import services

    # paid_payment est un SUCCESS à 1000 FCFA (prix du forfait) — le prestataire voit le même montant : MATCH.
    fake_transactions = [{"reference": paid_payment.reference, "status": "SUCCESS", "amount": paid_payment.amount_xaf}]
    monkeypatch.setattr(services, "build_client_from_settings", lambda: FakeFinanceClient(transactions=fake_transactions))

    user = make_user("f@example.com", make_role("Finance", ["reconciliation.run", "reconciliation.view"]))
    client = auth_client(user)
    response = client.post(RECONCILE_RUN, {
        "period_from": str(timezone.localdate() - timezone.timedelta(days=1)),
        "period_to": str(timezone.localdate() + timezone.timedelta(days=1)),
    }, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    results = {item["internal_reference"]: item["result"] for item in body["items"]}
    assert results[paid_payment.reference] == "MATCH"


@pytest.mark.django_db
def test_reconciliation_flags_missing_and_unmatched_provider_transaction(auth_client, make_role, make_user, monkeypatch, paid_payment):
    from apps.finance import services

    # Le prestataire ne connaît pas notre paiement (MISSING) et a une transaction qu'on ne connaît pas (UNMATCHED_PROVIDER).
    monkeypatch.setattr(services, "build_client_from_settings", lambda: FakeFinanceClient(
        transactions=[{"reference": "HRS-UNKNOWN", "status": "SUCCESS", "amount": 5000}]
    ))
    user = make_user("f@example.com", make_role("Finance", ["reconciliation.run"]))
    response = auth_client(user).post(RECONCILE_RUN, {
        "period_from": str(timezone.localdate() - timezone.timedelta(days=1)),
        "period_to": str(timezone.localdate() + timezone.timedelta(days=1)),
    }, format="json")
    results = [item["result"] for item in response.json()["items"]]
    assert "MISSING" in results
    assert "UNMATCHED_PROVIDER" in results


@pytest.mark.django_db
def test_reports_today_week_month(auth_client, make_role, make_user, paid_payment):
    user = make_user("f@example.com", make_role("Finance", ["payments.export"]))
    client = auth_client(user)
    for range_key in ("today", "week", "month"):
        response = client.get(f"{REPORTS}?range={range_key}")
        assert response.status_code == 200
        assert response.json()["range"] == range_key


@pytest.mark.django_db
def test_custom_report_requires_dates(auth_client, make_role, make_user):
    user = make_user("f@example.com", make_role("Finance", ["payments.export"]))
    response = auth_client(user).get(f"{REPORTS}?range=custom")
    assert response.status_code == 422
