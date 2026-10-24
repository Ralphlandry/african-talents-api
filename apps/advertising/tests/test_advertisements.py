import pytest

from apps.advertising.models import Advertisement
from apps.media.models import MediaAsset

ADMIN_ADVERTISEMENTS = "/api/v1/advertisements/"
PUBLIC_ADVERTISEMENTS = "/api/v1/public/advertisements/"


def make_image():
    return MediaAsset.objects.create(
        file="uploads/test/ad-poster.png",
        original_name="ad-poster.png",
        kind=MediaAsset.KIND_IMAGE,
        mime_type="image/png",
        size_bytes=128,
    )


@pytest.mark.django_db
def test_advertisement_crud_requires_advertising_permissions(auth_client, make_role, make_user):
    user = make_user(
        "advertising@example.com",
        make_role("Publicité", ["advertising.view", "advertising.manage"]),
    )
    client = auth_client(user)
    image = make_image()

    created = client.post(
        ADMIN_ADVERTISEMENTS,
        {
            "title": "Billetterie ouverte",
            "image_id": str(image.pk),
            "placement": "both",
            "display_delay_seconds": 10,
            "dismissal_cooldown_hours": 24,
            "button_label": "Acheter maintenant",
            "button_url": "/billetterie",
            "is_active": True,
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["image"]["id"] == str(image.pk)

    updated = client.patch(
        f"{ADMIN_ADVERTISEMENTS}{created.json()['id']}/",
        {"is_active": False},
        format="json",
    )
    assert updated.status_code == 200 and updated.json()["is_active"] is False
    assert client.delete(f"{ADMIN_ADVERTISEMENTS}{created.json()['id']}/").status_code == 204
    assert not Advertisement.objects.filter(pk=created.json()["id"]).exists()


@pytest.mark.django_db
def test_advertisement_management_rejects_external_button_url(auth_client, make_role, make_user):
    user = make_user("manager@example.com", make_role("Gestionnaire", ["advertising.manage"]))
    image = make_image()

    response = auth_client(user).post(
        ADMIN_ADVERTISEMENTS,
        {"title": "Test", "image_id": str(image.pk), "button_url": "//example.org"},
        format="json",
    )
    assert response.status_code == 422
    assert "button_url" in response.json()["errors"]


@pytest.mark.django_db
def test_public_advertisements_only_returns_active_ads(api):
    image = make_image()
    Advertisement.objects.create(title="Active", image=image, is_active=True)
    Advertisement.objects.create(title="Clôturée", image=image, is_active=False)

    response = api.get(PUBLIC_ADVERTISEMENTS)
    assert response.status_code == 200
    assert [ad["title"] for ad in response.json()] == ["Active"]
    assert "display_delay_seconds" in response.json()[0]
    assert response.json()[0]["image"]["url"]
