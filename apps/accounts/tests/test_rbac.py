import pytest

from apps.accounts.models import Role, User
from apps.audit.models import AuditLog

ADMINS = "/api/v1/admins/"
ROLES = "/api/v1/roles/"


@pytest.mark.django_db
def test_permission_is_enforced_per_action(auth_client, make_role, make_user):
    viewer = make_user("v@example.com", make_role("Lecteur", ["admins.view"]))
    nobody = make_user("n@example.com", make_role("Vide", ["news.view"]))

    assert auth_client(viewer).get(ADMINS).status_code == 200
    forbidden = auth_client(nobody).get(ADMINS)
    assert forbidden.status_code == 403 and forbidden.json()["code"] == "PERMISSION_DENIED"
    # lecture seule : la création est refusée même pour qui peut lister
    assert auth_client(viewer).post(ADMINS, {}, format="json").status_code == 403


@pytest.mark.django_db
def test_denied_write_is_audited(auth_client, make_role, make_user):
    nobody = make_user("n@example.com", make_role("Vide", ["news.view"]))
    auth_client(nobody).post(ADMINS, {}, format="json")
    assert AuditLog.objects.filter(action="PERMISSION_DENIED", result="DENIED", actor=nobody).exists()


@pytest.mark.django_db
def test_super_admin_creates_admin_and_gets_one_time_temp_password(auth_client, super_admin, make_role, api):
    role = make_role("Contenu", ["news.view"])
    response = auth_client(super_admin).post(
        ADMINS, {"email": "New@Example.com", "full_name": "Nouveau", "role": str(role.pk)}, format="json"
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com" and body["must_change_password"] is True
    temporary = body["temporary_password"]
    assert AuditLog.objects.filter(action="ADMIN_CREATED", actor=super_admin).exists()
    # le mot de passe temporaire ne fuit jamais dans l'audit
    assert temporary not in str(list(AuditLog.objects.values_list("metadata", flat=True)))

    login = api.post("/api/v1/auth/login/", {"email": "new@example.com", "password": temporary}, format="json")
    assert login.status_code == 200 and login.json()["must_change_password"] is True


@pytest.mark.django_db
def test_duplicate_email_is_rejected(auth_client, super_admin, make_role):
    role = make_role("Contenu", ["news.view"])
    response = auth_client(super_admin).post(
        ADMINS, {"email": super_admin.email.upper(), "full_name": "Dup", "role": str(role.pk)}, format="json"
    )
    assert response.status_code == 422 and "email" in response.json()["errors"]


@pytest.mark.django_db
def test_cannot_escalate_privileges_via_role_assignment(auth_client, make_role, make_user, super_role):
    manager = make_user("m@example.com", make_role("Gestionnaire", ["admins.view", "admins.create", "news.view"]))
    stronger = make_role("Financier", ["payments.view"])
    weaker = make_role("Lecteur news", ["news.view"])
    client = auth_client(manager)

    payload = {"full_name": "X", "password": "Str0ng-Pass-123!"}
    assert client.post(ADMINS, {**payload, "email": "a@example.com", "role": str(stronger.pk)}, format="json").status_code == 403
    assert client.post(ADMINS, {**payload, "email": "b@example.com", "role": str(super_role.pk)}, format="json").status_code == 403
    assert client.post(ADMINS, {**payload, "email": "c@example.com", "role": str(weaker.pk)}, format="json").status_code == 201


@pytest.mark.django_db
def test_cannot_deactivate_or_delete_self_or_last_super_admin(auth_client, super_admin):
    client = auth_client(super_admin)
    assert client.post(f"{ADMINS}{super_admin.pk}/deactivate/").status_code == 403
    assert client.delete(f"{ADMINS}{super_admin.pk}/").status_code == 403
    assert User.objects.get(pk=super_admin.pk).is_active


@pytest.mark.django_db
def test_one_super_admin_can_deactivate_another_and_target_is_locked_out(auth_client, make_user, super_role, super_admin):
    other = make_user("other@example.com", super_role, full_name="Other")
    assert auth_client(super_admin).post(f"{ADMINS}{other.pk}/deactivate/").status_code == 200
    # le compte désactivé perd immédiatement l'accès, même avec un jeton encore valide
    assert auth_client(other).get("/api/v1/auth/me/").status_code == 401


@pytest.mark.django_db
def test_last_super_admin_guard_is_enforced_at_service_level(super_admin):
    """Défense en profondeur : le service refuse de retirer le dernier Super Admin actif."""
    from apps.accounts import services
    from apps.core.exceptions import ConflictError

    with pytest.raises(ConflictError):
        services._ensure_not_last_super_admin(super_admin)


@pytest.mark.django_db
def test_deactivating_admin_revokes_their_sessions(api, auth_client, super_admin, make_role, make_user, password):
    target = make_user("t@example.com", make_role("Contenu", ["news.view"]))
    api.post("/api/v1/auth/login/", {"email": target.email, "password": password}, format="json")
    token = api.cookies["at_refresh"].value

    assert auth_client(super_admin).post(f"{ADMINS}{target.pk}/deactivate/").status_code == 200
    api.cookies["at_refresh"] = token
    assert api.post("/api/v1/auth/refresh/").status_code == 401


@pytest.mark.django_db
def test_reset_password_returns_temp_and_forces_change(auth_client, super_admin, make_role, make_user, api):
    target = make_user("t@example.com", make_role("Contenu", ["news.view"]))
    response = auth_client(super_admin).post(f"{ADMINS}{target.pk}/reset-password/")
    assert response.status_code == 200
    temporary = response.json()["temporary_password"]
    login = api.post("/api/v1/auth/login/", {"email": target.email, "password": temporary}, format="json")
    assert login.status_code == 200 and login.json()["must_change_password"] is True


@pytest.mark.django_db
def test_role_crud_and_protection(auth_client, super_admin, make_user, make_role, super_role):
    client = auth_client(super_admin)
    created = client.post(
        ROLES, {"name": "Gestionnaire Contenu", "description": "d", "permissions": ["news.view", "news.publish"]},
        format="json",
    )
    assert created.status_code == 201
    role_id = created.json()["id"]
    assert created.json()["slug"] == "gestionnaire-contenu"

    bad_code = client.post(ROLES, {"name": "Bad", "permissions": ["nope.nope"]}, format="json")
    assert bad_code.status_code == 422

    updated = client.patch(f"{ROLES}{role_id}/", {"permissions": ["news.view"]}, format="json")
    assert updated.status_code == 200 and updated.json()["permissions"] == ["news.view"]

    assert client.patch(f"{ROLES}{super_role.pk}/", {"name": "Hack"}, format="json").status_code == 403
    assert client.delete(f"{ROLES}{super_role.pk}/").status_code == 403

    make_user("u@example.com", Role.objects.get(pk=role_id))
    in_use = client.delete(f"{ROLES}{role_id}/")
    assert in_use.status_code == 409 and in_use.json()["code"] == "ROLE_IN_USE"


@pytest.mark.django_db
def test_non_super_admin_cannot_grant_permissions_they_lack(auth_client, make_role, make_user):
    manager = make_user("m@example.com", make_role("Roles mgr", ["admins.permissions", "news.view"]))
    response = auth_client(manager).post(ROLES, {"name": "Trop", "permissions": ["payments.view"]}, format="json")
    assert response.status_code == 403 and response.json()["code"] == "ROLE_ESCALATION"


@pytest.mark.django_db
def test_permission_catalog_and_audit_endpoint(auth_client, super_admin, make_role, make_user):
    client = auth_client(super_admin)
    catalog = client.get("/api/v1/permissions/").json()
    assert catalog[0]["key"] == "candidates"
    assert any(p["codename"] == "votes.adjust" for g in catalog for p in g["permissions"])

    client.post(ADMINS, {"email": "x@example.com", "full_name": "X", "role": str(make_role("R", ["news.view"]).pk)}, format="json")
    logs = client.get("/api/v1/audit-logs/?action=ADMIN_CREATED").json()
    assert logs["count"] == 1 and logs["results"][0]["module_label"] == "Administration"

    plain = make_user("p@example.com", make_role("Sans audit", ["news.view"]))
    assert auth_client(plain).get("/api/v1/audit-logs/").status_code == 403


@pytest.mark.django_db
def test_audit_log_is_append_only(super_admin):
    from apps.audit.services import record

    entry = record(actor=super_admin, action="X", module="administration")
    entry.action = "Y"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.filter(pk=entry.pk).update(action="Z")
