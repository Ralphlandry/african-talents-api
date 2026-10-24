import pytest

PACKAGES = "/api/v1/vote-packages/"
ADJUST = "/api/v1/votes/adjust/"
RANKINGS = "/api/v1/rankings/"


@pytest.mark.django_db
def test_admin_defines_package_quantity_and_price(auth_client, make_role, make_user, make_competition):
    """Décision B : c'est l'admin qui définit quantité + prix, pas un prix fixe codé en dur."""
    competition = make_competition()
    user = make_user("v@example.com", make_role("Votes", ["vote_packages.view", "vote_packages.create"]))
    response = auth_client(user).post(PACKAGES, {
        "competition": str(competition.pk), "label": "Pack 50", "quantity": 50, "price_xaf": 4500,
    }, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["quantity"] == 50 and body["price_xaf"] == 4500


@pytest.mark.django_db
def test_package_quantity_and_price_must_be_positive(auth_client, make_role, make_user, make_competition):
    competition = make_competition()
    user = make_user("v@example.com", make_role("Votes", ["vote_packages.create"]))
    client = auth_client(user)
    bad_qty = client.post(PACKAGES, {"competition": str(competition.pk), "label": "X", "quantity": 0, "price_xaf": 100}, format="json")
    bad_price = client.post(PACKAGES, {"competition": str(competition.pk), "label": "X", "quantity": 1, "price_xaf": 0}, format="json")
    assert bad_qty.status_code == 422 and bad_price.status_code == 422


@pytest.mark.django_db
def test_package_in_use_cannot_be_deleted(auth_client, make_role, make_user, make_competition, make_category, make_candidate, make_vote_package, make_vote_order):
    competition = make_competition()
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition)
    make_vote_order(candidate, package)
    user = make_user("v@example.com", make_role("Votes", ["vote_packages.delete"]))
    response = auth_client(user).delete(f"{PACKAGES}{package.pk}/")
    assert response.status_code == 409 and response.json()["code"] == "PACKAGE_IN_USE"


@pytest.mark.django_db
def test_create_order_is_idempotent(make_competition, make_category, make_candidate, make_vote_package):
    from apps.voting.services import create_order

    competition = make_competition(votes_open=True)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition, quantity=10, price_xaf=1000)

    order1, created1 = create_order(candidate=candidate, vote_package=package, phone="+237655500001", operator="MTN", idempotency_key="key-1")
    order2, created2 = create_order(candidate=candidate, vote_package=package, phone="+237655500001", operator="MTN", idempotency_key="key-1")
    assert created1 is True and created2 is False
    assert order1.pk == order2.pk
    assert order1.amount_xaf == 1000 and order1.quantity == 10
    assert order1.order_number.startswith("AT-")


@pytest.mark.django_db
def test_create_order_rejects_closed_votes(make_competition, make_category, make_candidate, make_vote_package):
    from apps.core.exceptions import UnprocessableError
    from apps.voting.services import create_order

    competition = make_competition(votes_open=False)
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    package = make_vote_package(competition)

    with pytest.raises(UnprocessableError) as exc_info:
        create_order(candidate=candidate, vote_package=package, phone="+237655500001", operator="MTN", idempotency_key="key-2")
    assert exc_info.value.error_code == "VOTES_CLOSED"


@pytest.mark.django_db
def test_create_order_rejects_package_from_another_competition(make_competition, make_category, make_candidate, make_vote_package):
    from apps.core.exceptions import UnprocessableError
    from apps.voting.services import create_order

    competition_a = make_competition(name="A", is_current=True, votes_open=True)
    competition_b = make_competition(name="B", is_current=False, votes_open=True)
    category = make_category(competition=competition_a)
    candidate = make_candidate(competition_a, category)
    foreign_package = make_vote_package(competition_b)

    with pytest.raises(UnprocessableError) as exc_info:
        create_order(candidate=candidate, vote_package=foreign_package, phone="+237655500001", operator="MTN", idempotency_key="key-3")
    assert exc_info.value.error_code == "PACKAGE_MISMATCH"


@pytest.mark.django_db
def test_manual_vote_adjustment_requires_reason(auth_client, make_role, make_user, make_competition, make_category, make_candidate):
    competition = make_competition()
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)
    user = make_user("v@example.com", make_role("Votes", ["votes.adjust"]))
    client = auth_client(user)

    too_short = client.post(ADJUST, {"candidate": str(candidate.pk), "delta": 5, "reason": "x"}, format="json")
    assert too_short.status_code == 422

    zero_delta = client.post(ADJUST, {"candidate": str(candidate.pk), "delta": 0, "reason": "Correction erreur de saisie"}, format="json")
    assert zero_delta.status_code == 422

    ok = client.post(ADJUST, {"candidate": str(candidate.pk), "delta": 25, "reason": "Correction erreur de saisie"}, format="json")
    assert ok.status_code == 201 and ok.json()["source"] == "MANUAL_ADJUSTMENT"


@pytest.mark.django_db
def test_historical_votes_can_only_be_imported_once_per_candidate(
    auth_client, make_role, make_user, make_competition, make_category, make_candidate
):
    user = make_user("historical-votes@example.com", make_role("Import historique", ["votes.adjust"]))
    competition = make_competition()
    candidate = make_candidate(competition, make_category(competition=competition))
    client = auth_client(user)
    payload = {
        "candidate": str(candidate.pk),
        "delta": 125,
        "reason": "Import des votes de l’ancien site",
    }

    first_import = client.post(ADJUST, payload, format="json")
    duplicate_import = client.post(ADJUST, payload, format="json")

    assert first_import.status_code == 201
    assert first_import.json()["quantity"] == 125
    assert duplicate_import.status_code == 409
    assert duplicate_import.json()["code"] == "HISTORICAL_VOTES_ALREADY_IMPORTED"


@pytest.mark.django_db
def test_ranking_reflects_ledger_not_a_denormalized_counter(auth_client, make_role, make_user, make_competition, make_category, make_candidate):
    from apps.voting.models import Vote

    competition = make_competition()
    category = make_category(competition=competition)
    c1 = make_candidate(competition, category, code="AT-001")
    c2 = make_candidate(competition, category, code="AT-002")
    Vote.objects.create(candidate=c1, quantity=10, source=Vote.PAID)
    Vote.objects.create(candidate=c1, quantity=5, source=Vote.PAID)
    Vote.objects.create(candidate=c2, quantity=12, source=Vote.PAID)

    user = make_user("v@example.com", make_role("Votes", ["rankings.view"]))
    response = auth_client(user).get(RANKINGS)
    ranking = response.json()
    assert ranking[0]["code"] == "AT-001" and ranking[0]["votes_total"] == 15
    assert ranking[1]["code"] == "AT-002" and ranking[1]["votes_total"] == 12


@pytest.mark.django_db
def test_ranking_endpoint_requires_permission(auth_client, make_role, make_user):
    nobody = make_user("n@example.com", make_role("Rien", []))
    assert auth_client(nobody).get(RANKINGS).status_code == 403
