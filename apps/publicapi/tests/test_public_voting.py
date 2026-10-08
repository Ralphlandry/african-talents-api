import pytest

PUBLIC = "/api/v1/public"


class FakeGatewayClient:
    def __init__(self, payin_result=None, status_result=None):
        self.payin_result = payin_result or {"status": "PENDING", "provider_reference": "HRS-1", "fees_xaf": None, "net_amount_xaf": None}
        self.status_result = status_result or {"status": "PENDING"}

    def create_mobile_money_payin(self, **kwargs):
        return self.payin_result

    def get_payment_status(self, reference):
        return self.status_result


@pytest.mark.django_db
def test_public_vote_packages_only_show_active_ones_of_current_competition(make_competition, make_vote_package, api):
    current = make_competition(name="Actuelle", is_current=True)
    other = make_competition(name="Autre", is_current=False)
    make_vote_package(current, label="10 votes", quantity=10, price_xaf=1000, is_active=True)
    make_vote_package(current, label="Ancien", is_active=False)
    make_vote_package(other, label="Pas la bonne compétition")

    response = api.get(f"{PUBLIC}/vote-packages/")
    labels = [p["label"] for p in response.json()]
    assert labels == ["10 votes"]


@pytest.mark.django_db
def test_full_public_vote_flow(monkeypatch, api, make_competition, make_category, make_candidate, make_vote_package):
    from apps.payments import services as payment_services

    monkeypatch.setattr(payment_services, "build_client_from_settings", lambda: FakeGatewayClient())

    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category, code="AT-001")
    package = make_vote_package(competition, quantity=10, price_xaf=1000)

    created = api.post(f"{PUBLIC}/vote-orders/", {
        "candidate": candidate.slug, "vote_package": str(package.pk), "phone": "+237655500001",
        "operator": "MTN", "idempotency_key": "public-flow-key-1", "accept_terms": True,
    }, format="json")
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "PENDING" and body["amount_xaf"] == 1000 and body["quantity"] == 10
    order_number = body["order_number"]

    polled = api.get(f"{PUBLIC}/vote-orders/{order_number}/")
    assert polled.status_code == 200 and polled.json()["order_number"] == order_number


@pytest.mark.django_db
def test_public_status_poll_syncs_provider_success(monkeypatch, api, make_competition, make_category, make_candidate, make_vote_package):
    from apps.payments import services as payment_services
    from apps.voting.models import Vote

    fake = FakeGatewayClient(
        status_result={"status": "SUCCESS", "amount_xaf": 1000, "fees_xaf": 0, "net_amount_xaf": 1000},
    )
    monkeypatch.setattr(payment_services, "build_client_from_settings", lambda: fake)

    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition, quantity=10, price_xaf=1000)
    created = api.post(f"{PUBLIC}/vote-orders/", {
        "candidate": candidate.slug, "vote_package": str(package.pk), "phone": "+237655500001",
        "operator": "ORANGE", "idempotency_key": "public-sync-success", "accept_terms": True,
    }, format="json")
    order_number = created.json()["order_number"]

    polled = api.get(f"{PUBLIC}/vote-orders/{order_number}/")

    assert polled.json()["status"] == "PAID"
    assert Vote.objects.get(vote_order__order_number=order_number).quantity == 10


@pytest.mark.django_db
def test_public_order_rejects_terms_not_accepted(api, make_competition, make_category, make_candidate, make_vote_package):
    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition)

    response = api.post(f"{PUBLIC}/vote-orders/", {
        "candidate": candidate.slug, "vote_package": str(package.pk), "phone": "+237655500001",
        "operator": "MTN", "idempotency_key": "key-no-terms", "accept_terms": False,
    }, format="json")
    assert response.status_code == 422


@pytest.mark.django_db
def test_public_order_rejects_unpublished_candidate(api, make_competition, make_category, make_candidate, make_vote_package):
    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    draft_candidate = make_candidate(competition, category, status="draft")
    package = make_vote_package(competition)

    response = api.post(f"{PUBLIC}/vote-orders/", {
        "candidate": draft_candidate.slug, "vote_package": str(package.pk), "phone": "+237655500001",
        "operator": "MTN", "idempotency_key": "key-draft", "accept_terms": True,
    }, format="json")
    assert response.status_code == 422  # le candidat "draft" n'existe pas dans le queryset public


@pytest.mark.django_db
def test_public_order_amount_always_comes_from_the_package_never_the_client(monkeypatch, api, make_competition, make_category, make_candidate, make_vote_package):
    """Le client ne peut PAS injecter son propre prix/quantité : seul l'id du forfait compte."""
    from apps.payments import services as payment_services

    monkeypatch.setattr(payment_services, "build_client_from_settings", lambda: FakeGatewayClient())
    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition, quantity=10, price_xaf=1000)

    response = api.post(f"{PUBLIC}/vote-orders/", {
        "candidate": candidate.slug, "vote_package": str(package.pk), "phone": "+237655500001",
        "operator": "MTN", "idempotency_key": "key-injection",
        "accept_terms": True,
        # tentative d'injection — ces champs n'existent même pas dans le sérialiseur, donc ignorés
        "amount_xaf": 1, "quantity": 999999,
    }, format="json")
    assert response.status_code == 201
    assert response.json()["amount_xaf"] == 1000 and response.json()["quantity"] == 10


@pytest.mark.django_db
def test_ranking_and_candidate_detail_reflect_real_votes(api, make_competition, make_category, make_candidate):
    from apps.voting.models import Vote

    competition = make_competition()
    category = make_category(competition=competition)
    c1 = make_candidate(competition, category, code="AT-001")
    c2 = make_candidate(competition, category, code="AT-002")
    Vote.objects.create(candidate=c1, quantity=30, source=Vote.PAID)
    Vote.objects.create(candidate=c2, quantity=10, source=Vote.PAID)

    ranking = api.get(f"{PUBLIC}/rankings/").json()
    assert [r["code"] for r in ranking] == ["AT-001", "AT-002"]

    detail = api.get(f"{PUBLIC}/candidates/{c1.slug}/").json()
    assert detail["votes_total"] == 30 and detail["rank"] == 1
