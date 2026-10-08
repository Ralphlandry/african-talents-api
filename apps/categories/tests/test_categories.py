import pytest

CATEGORIES = "/api/v1/categories/"


@pytest.mark.django_db
def test_category_crud_and_publish(auth_client, make_role, make_user, make_competition):
    competition = make_competition()
    user = make_user("c@example.com", make_role(
        "Cat", ["categories.view", "categories.create", "categories.edit", "categories.publish", "categories.delete"]
    ))
    client = auth_client(user)

    created = client.post(CATEGORIES, {"competition": str(competition.pk), "name": "Mode & Design"}, format="json")
    assert created.status_code == 201
    body = created.json()
    assert body["slug"] == "mode-design" and body["status"] == "draft"

    published = client.post(f"{CATEGORIES}{body['id']}/publish/")
    assert published.status_code == 200 and published.json()["status"] == "published"

    assert client.delete(f"{CATEGORIES}{body['id']}/").status_code == 204


@pytest.mark.django_db
def test_reorder_categories(auth_client, make_role, make_user, make_competition, make_category):
    competition = make_competition()
    a = make_category("A", competition=competition)
    b = make_category("B", competition=competition)
    user = make_user("c@example.com", make_role("Cat", ["categories.view", "categories.edit"]))
    client = auth_client(user)

    response = client.post(f"{CATEGORIES}reorder/", {"ordered_ids": [str(b.pk), str(a.pk)]}, format="json")
    assert response.status_code == 200
    b.refresh_from_db()
    a.refresh_from_db()
    assert b.order == 1 and a.order == 2


@pytest.mark.django_db
def test_category_write_requires_permission(auth_client, make_role, make_user):
    viewer = make_user("v@example.com", make_role("Lecteur", ["categories.view"]))
    response = auth_client(viewer).post(CATEGORIES, {"name": "X"}, format="json")
    assert response.status_code == 403
