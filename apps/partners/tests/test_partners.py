import pytest

from apps.media.models import MediaAsset
from apps.partners.models import Partner

PARTNERS = "/api/v1/partners/"
PUBLIC_PARTNERS = "/api/v1/public/partners/"


def make_logo():
    return MediaAsset.objects.create(
        file="uploads/test/partner-logo.png", original_name="partner-logo.png", kind=MediaAsset.KIND_IMAGE,
        mime_type="image/png", size_bytes=128,
    )


@pytest.mark.django_db
def test_partner_crud_requires_permissions_and_logo(auth_client, make_role, make_user):
    user = make_user("partners@example.com", make_role(
        "Partners", ["partners.view", "partners.create", "partners.edit", "partners.delete"]
    ))
    client = auth_client(user)
    logo = make_logo()

    created = client.post(PARTNERS, {"name": "Entreprise Africa", "logo_id": str(logo.pk)}, format="json")
    assert created.status_code == 201
    assert created.json()["name"] == "Entreprise Africa"
    assert created.json()["logo"]["id"] == str(logo.pk)
    assert created.json()["order"] == 1

    updated = client.patch(f"{PARTNERS}{created.json()['id']}/", {"name": "Entreprise Africa SA"}, format="json")
    assert updated.status_code == 200 and updated.json()["name"] == "Entreprise Africa SA"
    assert client.delete(f"{PARTNERS}{created.json()['id']}/").status_code == 204
    assert not Partner.objects.filter(pk=created.json()["id"]).exists()


@pytest.mark.django_db
def test_public_partner_list_returns_only_visible_partners(api):
    logo = make_logo()
    Partner.objects.create(name="Visible SA", logo=logo, order=1, is_visible=True)
    Partner.objects.create(name="Masqué SA", logo=logo, order=2, is_visible=False)

    response = api.get(PUBLIC_PARTNERS)
    assert response.status_code == 200
    assert [row["name"] for row in response.json()] == ["Visible SA"]
    assert response.json()[0]["logo"]["id"] == str(logo.pk)
