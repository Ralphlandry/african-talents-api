import pytest

TEAM = "/api/v1/team/"


@pytest.mark.django_db
def test_team_member_crud_and_auto_order(auth_client, make_role, make_user):
    user = make_user("t@example.com", make_role("Team", ["team.view", "team.create", "team.edit", "team.delete"]))
    client = auth_client(user)

    first = client.post(TEAM, {"type": "coach", "full_name": "Coach 1"}, format="json")
    second = client.post(TEAM, {"type": "coach", "full_name": "Coach 2"}, format="json")
    assert first.json()["order"] == 1 and second.json()["order"] == 2

    updated = client.patch(f"{TEAM}{first.json()['id']}/", {"role_title": "Coach chant"}, format="json")
    assert updated.status_code == 200 and updated.json()["role_title"] == "Coach chant"

    assert client.delete(f"{TEAM}{second.json()['id']}/").status_code == 204


@pytest.mark.django_db
def test_team_member_custom_order_is_saved_and_used(auth_client, make_role, make_user):
    user = make_user("ordered@example.com", make_role("Team Order", ["team.view", "team.create", "team.edit"]))
    client = auth_client(user)

    first = client.post(TEAM, {"type": "team", "full_name": "Premier", "order": 2}, format="json")
    second = client.post(TEAM, {"type": "team", "full_name": "Deuxième"}, format="json")

    assert first.status_code == 201
    assert first.json()["order"] == 2
    assert second.status_code == 201
    assert second.json()["order"] == 3

    updated = client.patch(f"{TEAM}{first.json()['id']}/", {"order": 1}, format="json")
    assert updated.status_code == 200
    assert updated.json()["order"] == 1

    invalid = client.patch(f"{TEAM}{first.json()['id']}/", {"order": 0}, format="json")
    assert invalid.status_code == 400
