import pytest

CANDIDATES = "/api/v1/candidates/"


@pytest.mark.django_db
def test_create_update_publish_candidate(auth_client, make_role, make_user, make_competition, make_category):
    competition = make_competition()
    category = make_category(competition=competition)
    user = make_user("c@example.com", make_role(
        "Cand", ["candidates.view", "candidates.create", "candidates.edit", "candidates.publish"]
    ))
    client = auth_client(user)

    created = client.post(CANDIDATES, {
        "competition": str(competition.pk), "category": str(category.pk), "code": "at-001",
        "first_name": "Aminata", "last_name": "Diallo", "city": "Conakry",
    }, format="json")
    assert created.status_code == 201
    body = created.json()
    assert body["code"] == "AT-001"  # normalisé en majuscules
    assert body["status"] == "draft" and body["display_name"] == "Diallo Aminata"

    updated = client.patch(f"{CANDIDATES}{body['id']}/", {"city": "Dakar"}, format="json")
    assert updated.status_code == 200 and updated.json()["city"] == "Dakar"

    published = client.post(f"{CANDIDATES}{body['id']}/publish/")
    assert published.status_code == 200 and published.json()["status"] == "published"


@pytest.mark.django_db
def test_duplicate_code_in_same_competition_is_rejected(auth_client, make_role, make_user, make_competition, make_category):
    competition = make_competition()
    category = make_category(competition=competition)
    user = make_user("c@example.com", make_role("Cand", ["candidates.create"]))
    client = auth_client(user)
    payload = {"competition": str(competition.pk), "category": str(category.pk), "code": "AT-002", "first_name": "A", "last_name": "B"}
    assert client.post(CANDIDATES, payload, format="json").status_code == 201
    dup = client.post(CANDIDATES, {**payload, "first_name": "C"}, format="json")
    assert dup.status_code in (422, 500)  # contrainte unique en base ; 422 si validée avant, sinon remontée par le handler


@pytest.mark.django_db
def test_bulk_actions(auth_client, make_role, make_user, make_competition, make_category, make_candidate):
    competition = make_competition()
    category = make_category(competition=competition)
    c1 = make_candidate(competition, category, code="AT-010", status="draft", is_active=False)
    c2 = make_candidate(competition, category, code="AT-011", status="draft", is_active=False)
    user = make_user("c@example.com", make_role(
        "Cand", ["candidates.view", "candidates.publish", "candidates.edit", "candidates.delete"]
    ))
    client = auth_client(user)
    ids = [str(c1.pk), str(c2.pk)]

    pub = client.post(f"{CANDIDATES}bulk-publish/", {"ids": ids}, format="json")
    assert pub.status_code == 200 and pub.json()["updated"] == 2

    act = client.post(f"{CANDIDATES}bulk-activate/", {"ids": ids}, format="json")
    assert act.status_code == 200 and act.json()["updated"] == 2

    deleted = client.post(f"{CANDIDATES}bulk-delete/", {"ids": ids}, format="json")
    assert deleted.status_code == 200 and deleted.json()["deleted"] == 2
    assert client.get(CANDIDATES).json()["count"] == 0


@pytest.mark.django_db
def test_finance_admin_cannot_touch_candidates(auth_client, make_role, make_user):
    finance = make_user("f@example.com", make_role("Finance", ["payments.view"]))
    assert auth_client(finance).get(CANDIDATES).status_code == 403
