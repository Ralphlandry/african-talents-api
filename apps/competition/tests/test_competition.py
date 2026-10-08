import pytest

COMPETITIONS = "/api/v1/competitions/"


@pytest.mark.django_db
def test_create_competition_and_only_one_is_current(auth_client, make_role, make_user, make_competition):
    old = make_competition(name="Ancienne", is_current=True)
    user = make_user("c@example.com", make_role("Compet", ["competition.view", "competition.edit", "competition.start"]))
    client = auth_client(user)

    created = client.post(COMPETITIONS, {
        "name": "Nouvelle Saison", "description": "d", "start_date": "2027-01-01", "end_date": "2027-06-01",
    }, format="json")
    assert created.status_code == 201
    new_id = created.json()["id"]

    started = client.post(f"{COMPETITIONS}{new_id}/start/")
    assert started.status_code == 200 and started.json()["is_current"] is True

    old.refresh_from_db()
    assert old.is_current is False  # une seule compétition "courante" à la fois


@pytest.mark.django_db
def test_end_date_before_start_date_is_rejected(auth_client, make_role, make_user):
    user = make_user("c@example.com", make_role("Compet", ["competition.edit"]))
    response = auth_client(user).post(COMPETITIONS, {
        "name": "Invalide", "start_date": "2027-06-01", "end_date": "2027-01-01",
    }, format="json")
    assert response.status_code == 422


@pytest.mark.django_db
def test_phase_crud_and_active_phase_cannot_be_deleted(auth_client, make_role, make_user, make_competition):
    competition = make_competition()
    user = make_user("c@example.com", make_role("Compet", ["competition.view", "competition.edit"]))
    client = auth_client(user)
    base = f"{COMPETITIONS}{competition.pk}/"

    created = client.post(f"{base}phases/", {
        "name": "Sélection", "start_date": "2026-01-01", "end_date": "2026-01-31", "status": "active",
    }, format="json")
    assert created.status_code == 201
    phase_id = created.json()["id"]

    updated = client.patch(f"{base}phases/{phase_id}/", {"name": "Sélection (renommée)"}, format="json")
    assert updated.status_code == 200 and updated.json()["name"] == "Sélection (renommée)"

    blocked = client.delete(f"{base}phases/{phase_id}/")
    assert blocked.status_code == 409 and blocked.json()["code"] == "PHASE_ACTIVE"

    client.patch(f"{base}phases/{phase_id}/", {"status": "terminee"}, format="json")
    assert client.delete(f"{base}phases/{phase_id}/").status_code == 204


@pytest.mark.django_db
def test_toggle_votes(auth_client, make_role, make_user, make_competition):
    competition = make_competition(votes_open=False)
    user = make_user("c@example.com", make_role("Compet", ["competition.view", "competition.edit"]))
    client = auth_client(user)
    response = client.post(f"{COMPETITIONS}{competition.pk}/toggle-votes/")
    assert response.status_code == 200 and response.json()["votes_open"] is True
