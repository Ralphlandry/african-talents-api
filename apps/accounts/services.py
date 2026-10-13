"""Règles métier de gestion des comptes et rôles (jamais dans les vues)."""
import secrets
import string

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils.text import slugify
from rest_framework import serializers
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from apps.audit.constants import AuditAction as A
from apps.audit.constants import AuditModule as M
from apps.audit.services import record
from apps.core.exceptions import ConflictError, ForbiddenError

from .models import Role, User

# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------


def generate_temporary_password(length=14):
    alphabet = string.ascii_letters + string.digits + "-_!@#"
    while True:
        candidate = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
        ):
            return candidate


def revoke_all_sessions(user):
    """Invalide tous les refresh tokens du compte (déconnexion de tous les appareils)."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)


def _validate_password_or_422(password, user=None):
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)})


def _role_permission_keys(role):
    return set(role.permissions.values_list("codename", flat=True))


# ---------------------------------------------------------------------------
# Garde-fous anti-escalade de privilèges
# ---------------------------------------------------------------------------


def assert_can_assign_role(actor, role):
    if actor.is_super_admin:
        return
    if role.is_super_admin:
        raise ForbiddenError("Seul un Super Administrateur peut attribuer ce rôle.", code="ROLE_ESCALATION")
    if not _role_permission_keys(role).issubset(actor.get_permission_keys()):
        raise ForbiddenError(
            "Vous ne pouvez pas attribuer un rôle contenant des permissions que vous ne possédez pas.",
            code="ROLE_ESCALATION",
        )


def assert_can_manage(actor, target):
    if target.is_super_admin and not actor.is_super_admin:
        raise ForbiddenError("Seul un Super Administrateur peut modifier ce compte.", code="TARGET_PROTECTED")


def _forbid_self(actor, target, message):
    if actor.pk == target.pk:
        raise ForbiddenError(message, code="SELF_ACTION_FORBIDDEN")


def _ensure_not_last_super_admin(target):
    if target.is_super_admin and target.is_active:
        others = User.objects.filter(role__is_super_admin=True, is_active=True).exclude(pk=target.pk).exists()
        if not others:
            raise ConflictError("Il doit rester au moins un Super Administrateur actif.", code="LAST_SUPER_ADMIN")


# ---------------------------------------------------------------------------
# Administrateurs
# ---------------------------------------------------------------------------


@transaction.atomic
def create_admin(actor, *, email, full_name, role, password=None, is_active=True, request=None):
    assert_can_assign_role(actor, role)
    temporary = None
    if password:
        _validate_password_or_422(password)
    else:
        temporary = password = generate_temporary_password()
    user = User.objects.create_user(
        email=email, password=password, full_name=full_name, role=role,
        is_active=is_active, must_change_password=True, created_by=actor,
    )
    record(request=request, actor=actor, action=A.ADMIN_CREATED, module=M.ADMINISTRATION,
           resource="user", resource_id=user.pk, metadata={"email": user.email, "role": role.slug})
    return user, temporary


@transaction.atomic
def update_admin(actor, target, *, full_name=None, role=None, is_active=None, request=None):
    assert_can_manage(actor, target)
    changes = {}
    if full_name is not None and full_name != target.full_name:
        changes["full_name"] = full_name
        target.full_name = full_name
    if role is not None and role.pk != target.role_id:
        _forbid_self(actor, target, "Vous ne pouvez pas modifier votre propre rôle.")
        assert_can_assign_role(actor, role)
        if target.is_super_admin and not role.is_super_admin:
            _ensure_not_last_super_admin(target)
        changes["role"] = role.slug
        target.role = role
        revoke_all_sessions(target)
    if changes:
        target.save()
        record(request=request, actor=actor, action=A.ADMIN_UPDATED, module=M.ADMINISTRATION,
               resource="user", resource_id=target.pk, metadata={"email": target.email, "changes": changes})
    if is_active is not None and is_active != target.is_active:
        set_active(actor, target, is_active, request=request)
    return target


@transaction.atomic
def set_active(actor, target, active, *, request=None):
    assert_can_manage(actor, target)
    if not active:
        _forbid_self(actor, target, "Vous ne pouvez pas désactiver votre propre compte.")
        _ensure_not_last_super_admin(target)
    target.is_active = active
    target.save(update_fields=["is_active", "updated_at"])
    if not active:
        revoke_all_sessions(target)
    record(request=request, actor=actor, action=A.ADMIN_ACTIVATED if active else A.ADMIN_DEACTIVATED,
           module=M.ADMINISTRATION, resource="user", resource_id=target.pk, metadata={"email": target.email})
    return target


@transaction.atomic
def delete_admin(actor, target, *, request=None):
    assert_can_manage(actor, target)
    _forbid_self(actor, target, "Vous ne pouvez pas supprimer votre propre compte.")
    _ensure_not_last_super_admin(target)
    email, pk = target.email, target.pk
    target.delete()
    record(request=request, actor=actor, action=A.ADMIN_DELETED, module=M.ADMINISTRATION,
           resource="user", resource_id=pk, metadata={"email": email})


@transaction.atomic
def reset_password(actor, target, *, request=None):
    assert_can_manage(actor, target)
    _forbid_self(actor, target, "Utilisez « changer mon mot de passe » pour votre propre compte.")
    temporary = generate_temporary_password()
    target.set_password(temporary)
    target.must_change_password = True
    target.failed_login_count = 0
    target.locked_until = None
    target.save()
    revoke_all_sessions(target)
    record(request=request, actor=actor, action=A.ADMIN_PASSWORD_RESET, module=M.ADMINISTRATION,
           resource="user", resource_id=target.pk, metadata={"email": target.email})
    return temporary


# ---------------------------------------------------------------------------
# Rôles
# ---------------------------------------------------------------------------


def _unique_slug(name):
    base = slugify(name)[:120] or "role"
    slug, n = base, 2
    while Role.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug


def _assert_permissions_grantable(actor, permissions):
    if actor.is_super_admin:
        return
    codenames = {p.codename for p in permissions}
    if not codenames.issubset(actor.get_permission_keys()):
        raise ForbiddenError("Vous ne pouvez pas accorder des permissions que vous ne possédez pas.", code="ROLE_ESCALATION")


@transaction.atomic
def create_role(actor, *, name, description="", color="blue", permissions=(), request=None):
    permissions = list(permissions)
    _assert_permissions_grantable(actor, permissions)
    role = Role.objects.create(name=name, slug=_unique_slug(name), description=description, color=color)
    role.permissions.set(permissions)
    record(request=request, actor=actor, action=A.ROLE_CREATED, module=M.ADMINISTRATION,
           resource="role", resource_id=role.pk,
           metadata={"name": role.name, "permissions": sorted(p.codename for p in permissions)})
    return role


@transaction.atomic
def update_role(actor, role, *, name=None, description=None, color=None, permissions=None, request=None):
    if role.is_system:
        raise ForbiddenError("Ce rôle système ne peut pas être modifié.", code="SYSTEM_ROLE_PROTECTED")
    if not actor.is_super_admin and not _role_permission_keys(role).issubset(actor.get_permission_keys()):
        raise ForbiddenError("Vous ne pouvez pas modifier un rôle plus puissant que le vôtre.", code="ROLE_ESCALATION")
    if name is not None:
        role.name = name
    if description is not None:
        role.description = description
    if color is not None:
        role.color = color
    role.save()
    if permissions is not None:
        permissions = list(permissions)
        _assert_permissions_grantable(actor, permissions)
        role.permissions.set(permissions)
        # les sessions des utilisateurs de ce rôle gardent leurs jetons, mais les droits sont relus en base à chaque requête
    record(request=request, actor=actor, action=A.ROLE_UPDATED, module=M.ADMINISTRATION, resource="role",
           resource_id=role.pk, metadata={"name": role.name,
                                          "permissions": sorted(_role_permission_keys(role))})
    return role


@transaction.atomic
def delete_role(actor, role, *, request=None):
    if role.is_system:
        raise ForbiddenError("Ce rôle système ne peut pas être supprimé.", code="SYSTEM_ROLE_PROTECTED")
    if role.users.exists():
        raise ConflictError("Ce rôle est attribué à des administrateurs et ne peut pas être supprimé.", code="ROLE_IN_USE")
    if not actor.is_super_admin and not _role_permission_keys(role).issubset(actor.get_permission_keys()):
        raise ForbiddenError("Vous ne pouvez pas supprimer un rôle plus puissant que le vôtre.", code="ROLE_ESCALATION")
    name, pk = role.name, role.pk
    role.delete()
    record(request=request, actor=actor, action=A.ROLE_DELETED, module=M.ADMINISTRATION,
           resource="role", resource_id=pk, metadata={"name": name})
