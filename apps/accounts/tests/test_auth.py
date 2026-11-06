from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail

from apps.accounts.models import User
from apps.audit.models import AuditLog

LOGIN = "/api/v1/auth/login/"
REFRESH = "/api/v1/auth/refresh/"
LOGOUT = "/api/v1/auth/logout/"
ME = "/api/v1/auth/me/"
CHANGE = "/api/v1/auth/change-password/"
PASSWORD_RESET = "/api/v1/auth/password-reset/"
PASSWORD_RESET_CONFIRM = "/api/v1/auth/password-reset/confirm/"


@pytest.mark.django_db
def test_login_success(api, super_admin, password):
    response = api.post(LOGIN, {"email": super_admin.email, "password": password}, format="json")
    assert response.status_code == 200
    body = response.json()
    assert body["access"] and "refresh" not in body
    assert body["user"]["permissions"] == ["*"]
    cookie = response.cookies["at_refresh"]
    assert cookie["httponly"] and cookie["path"] == "/api/v1/auth/"
    super_admin.refresh_from_db()
    assert super_admin.last_login is not None
    assert AuditLog.objects.filter(action="ADMIN_LOGIN", actor=super_admin, result="SUCCESS").exists()


@pytest.mark.django_db
def test_login_wrong_password_and_unknown_email_look_identical(api, super_admin):
    wrong = api.post(LOGIN, {"email": super_admin.email, "password": "nope-nope-nope"}, format="json")
    unknown = api.post(LOGIN, {"email": "ghost@example.com", "password": "nope-nope-nope"}, format="json")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "INVALID_CREDENTIALS"
    assert AuditLog.objects.filter(action="ADMIN_LOGIN_FAILED").count() == 2


@pytest.mark.django_db
def test_login_disabled_account(api, make_user, super_role, password):
    make_user("off@example.com", super_role, is_active=False)
    response = api.post(LOGIN, {"email": "off@example.com", "password": password}, format="json")
    assert response.status_code == 403
    assert response.json()["code"] == "ACCOUNT_DISABLED"


@pytest.mark.django_db
def test_lockout_after_repeated_failures(api, super_admin, password):
    for _ in range(5):
        api.post(LOGIN, {"email": super_admin.email, "password": "bad-bad-bad-1"}, format="json")
    response = api.post(LOGIN, {"email": super_admin.email, "password": password}, format="json")
    assert response.status_code == 429
    assert response.json()["code"] == "ACCOUNT_LOCKED"


@pytest.mark.django_db
def test_me_requires_auth_and_returns_permissions(api, auth_client, make_role, make_user, password):
    assert api.get(ME).status_code == 401
    role = make_role("Contenu", ["news.view", "news.create"])
    user = make_user("c@example.com", role)
    body = auth_client(user).get(ME).json()
    assert body["permissions"] == ["news.create", "news.view"]
    assert body["role"]["slug"] == "contenu"


@pytest.mark.django_db
def test_refresh_rotates_and_old_token_is_rejected(api, super_admin, password):
    login = api.post(LOGIN, {"email": super_admin.email, "password": password}, format="json")
    old_refresh = login.cookies["at_refresh"].value

    refreshed = api.post(REFRESH)
    assert refreshed.status_code == 200 and refreshed.json()["access"]
    assert refreshed.cookies["at_refresh"].value != old_refresh

    api.cookies["at_refresh"] = old_refresh  # rejeu de l'ancien jeton
    replay = api.post(REFRESH)
    assert replay.status_code == 401
    assert replay.json()["code"] == "TOKEN_INVALID"


@pytest.mark.django_db
def test_refresh_without_cookie_is_rejected(api):
    response = api.post(REFRESH)
    assert response.status_code == 400 and response.json()["code"] == "TOKEN_MISSING"


@pytest.mark.django_db
def test_logout_blacklists_refresh(api, super_admin, password):
    api.post(LOGIN, {"email": super_admin.email, "password": password}, format="json")
    token = api.cookies["at_refresh"].value
    assert api.post(LOGOUT).status_code == 204
    api.cookies["at_refresh"] = token
    assert api.post(REFRESH).status_code == 401


@pytest.mark.django_db
def test_deactivated_user_access_token_is_rejected_immediately(auth_client, super_admin):
    client = auth_client(super_admin)
    assert client.get(ME).status_code == 200
    User.objects.filter(pk=super_admin.pk).update(is_active=False)
    assert client.get(ME).status_code == 401


@pytest.mark.django_db
def test_change_password(auth_client, super_admin, password, api):
    client = auth_client(super_admin)
    bad = client.post(CHANGE, {"old_password": "wrong-wrong-1", "new_password": "An0ther-Str0ng-Pass!"}, format="json")
    assert bad.status_code == 422 and "old_password" in bad.json()["errors"]

    weak = client.post(CHANGE, {"old_password": password, "new_password": "12345678"}, format="json")
    assert weak.status_code == 422

    ok = client.post(CHANGE, {"old_password": password, "new_password": "An0ther-Str0ng-Pass!"}, format="json")
    assert ok.status_code == 200 and ok.json()["must_change_password"] is False
    assert api.post(LOGIN, {"email": super_admin.email, "password": password}, format="json").status_code == 401
    assert api.post(LOGIN, {"email": super_admin.email, "password": "An0ther-Str0ng-Pass!"}, format="json").status_code == 200


@pytest.mark.django_db
def test_password_reset_request_does_not_disclose_unknown_accounts(api, super_admin):
    unknown = api.post(PASSWORD_RESET, {"email": "ghost@example.com"}, format="json")
    known = api.post(PASSWORD_RESET, {"email": super_admin.email}, format="json")

    assert unknown.status_code == known.status_code == 200
    assert unknown.json() == known.json()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [super_admin.email]
    assert "reset-password?" in mail.outbox[0].body


@pytest.mark.django_db
def test_password_reset_link_changes_password_once_and_revokes_sessions(api, super_admin, password):
    login = api.post(LOGIN, {"email": super_admin.email, "password": password}, format="json")
    assert login.status_code == 200
    super_admin.must_change_password = True
    super_admin.failed_login_count = 3
    super_admin.save(update_fields=["must_change_password", "failed_login_count"])

    api.post(PASSWORD_RESET, {"email": super_admin.email}, format="json")
    reset_url = next(line for line in mail.outbox[0].body.splitlines() if line.startswith("http"))
    params = parse_qs(urlparse(reset_url).query)
    reset_data = {
        "uid": params["uid"][0],
        "token": params["token"][0],
        "new_password": "An0ther-Str0ng-Pass!",
    }

    weak = api.post(PASSWORD_RESET_CONFIRM, {**reset_data, "new_password": "12345678"}, format="json")
    assert weak.status_code == 422

    response = api.post(PASSWORD_RESET_CONFIRM, reset_data, format="json")
    assert response.status_code == 200
    assert api.post(REFRESH).status_code == 401
    super_admin.refresh_from_db()
    assert super_admin.check_password(reset_data["new_password"])
    assert not super_admin.must_change_password
    assert super_admin.failed_login_count == 0
    assert api.post(LOGIN, {"email": super_admin.email, "password": password}, format="json").status_code == 401
    assert api.post(LOGIN, {"email": super_admin.email, "password": reset_data["new_password"]}, format="json").status_code == 200

    reused = api.post(PASSWORD_RESET_CONFIRM, reset_data, format="json")
    assert reused.status_code == 422
    assert AuditLog.objects.filter(action="ADMIN_PASSWORD_RESET", actor=super_admin).exists()


@pytest.mark.django_db
def test_password_reset_rejects_invalid_or_inactive_accounts(api, make_user, super_role):
    inactive = make_user("inactive@example.com", super_role, is_active=False)
    response = api.post(PASSWORD_RESET, {"email": inactive.email}, format="json")
    assert response.status_code == 200
    assert not mail.outbox

    invalid = api.post(
        PASSWORD_RESET_CONFIRM,
        {"uid": "invalid", "token": "invalid", "new_password": "An0ther-Str0ng-Pass!"},
        format="json",
    )
    assert invalid.status_code == 422

    malformed_uuid = api.post(
        PASSWORD_RESET_CONFIRM,
        {"uid": "Zm9v", "token": "invalid", "new_password": "An0ther-Str0ng-Pass!"},
        format="json",
    )
    assert malformed_uuid.status_code == 422
