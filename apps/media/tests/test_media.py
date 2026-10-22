import pytest

MEDIA = "/api/v1/media/"


@pytest.mark.django_db
def test_upload_requires_permission(auth_client, make_role, make_user, uploaded_image):
    nobody = make_user("n@example.com", make_role("Sans droits", []))
    response = auth_client(nobody).post(MEDIA, {"file": uploaded_image()}, format="multipart")
    assert response.status_code == 403


@pytest.mark.django_db
def test_upload_and_list_and_delete(auth_client, make_role, make_user, uploaded_image):
    user = make_user("m@example.com", make_role("Media", ["media.view", "media.upload", "media.delete"]))
    client = auth_client(user)

    created = client.post(MEDIA, {"file": uploaded_image(), "usage": "candidate_photo"}, format="multipart")
    assert created.status_code == 201
    body = created.json()
    assert body["kind"] == "image" and body["original_name"] == "photo.jpg" and body["url"]

    listed = client.get(MEDIA).json()
    assert listed["count"] == 1

    deleted = client.delete(f"{MEDIA}{body['id']}/")
    assert deleted.status_code == 204
    assert client.get(MEDIA).json()["count"] == 0


@pytest.mark.django_db
def test_upload_rejects_disguised_file(auth_client, make_role, make_user):
    from django.core.files.uploadedfile import SimpleUploadedFile

    user = make_user("m@example.com", make_role("Media", ["media.upload"]))
    fake = SimpleUploadedFile("virus.jpg", b"MZ\x90\x00fake-exe-content", content_type="image/jpeg")
    response = auth_client(user).post(MEDIA, {"file": fake}, format="multipart")
    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_FILE"


@pytest.mark.django_db
def test_upload_rejects_oversized_file(auth_client, make_role, make_user):
    from django.core.files.uploadedfile import SimpleUploadedFile

    user = make_user("m@example.com", make_role("Media", ["media.upload"]))
    huge = SimpleUploadedFile(
        "big.jpg", bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"\x00" * (9 * 1024 * 1024),
        content_type="image/jpeg",
    )
    response = auth_client(user).post(MEDIA, {"file": huge}, format="multipart")
    assert response.status_code == 422
