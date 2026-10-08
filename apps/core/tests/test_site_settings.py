import pytest

SETTINGS = "/api/v1/settings/"


@pytest.mark.django_db
def test_settings_singleton_get_and_update(auth_client, make_role, make_user):
    user = make_user("s@example.com", make_role("Settings", ["settings.view", "settings.edit"]))
    client = auth_client(user)

    first = client.get(SETTINGS)
    assert first.status_code == 200 and first.json()["site_name"] == "African Talents"

    updated = client.patch(SETTINGS, {
        "tagline": "La plate-forme où vous êtes impactés pour impacter",
        "contact_email": "contact@africantalents.africa",
        "stats": [{"label": "Talents", "value": "300"}, {"label": "Pays", "value": "20"}],
    }, format="json")
    assert updated.status_code == 200
    assert updated.json()["stats"][1] == {"label": "Pays", "value": "20"}

    again = client.get(SETTINGS)
    assert again.json()["contact_email"] == "contact@africantalents.africa"  # bien persisté, pas juste renvoyé


@pytest.mark.django_db
def test_settings_view_requires_permission(auth_client, make_role, make_user):
    nobody = make_user("x@example.com", make_role("Rien", []))
    assert auth_client(nobody).get(SETTINGS).status_code == 403
