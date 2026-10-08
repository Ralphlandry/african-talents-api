import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import F
from django.utils import timezone

from apps.core.models import BaseModel


class Permission(BaseModel):
    """Permission granulaire `ressource.action` (catalogue défini dans catalog.py)."""

    codename = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=160)
    group = models.CharField(max_length=64, db_index=True)
    group_label = models.CharField(max_length=120)

    class Meta:
        ordering = ["group", "codename"]

    def __str__(self):
        return self.codename


class Role(BaseModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    color = models.CharField(max_length=16, default="blue")
    is_system = models.BooleanField(default=False)
    # Le Super Admin possède implicitement toutes les permissions (présentes et futures).
    is_super_admin = models.BooleanField(default=False)
    permissions = models.ManyToManyField(Permission, related_name="roles", blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("L'adresse e-mail est obligatoire.")
        if extra.get("role") is None and extra.get("role_id") is None:
            raise ValueError("Un rôle est obligatoire.")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_active", True)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        from .rbac import get_super_admin_role

        extra.setdefault("role", get_super_admin_role())
        extra.setdefault("is_active", True)
        return self._create(email, password, **extra)


class User(AbstractBaseUser):
    """Compte administrateur (le public ne se connecte jamais)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=160)
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="users")
    is_active = models.BooleanField(default=True)
    must_change_password = models.BooleanField(default=False)
    failed_login_count = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["full_name"]

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.email

    # -- rôle / permissions --------------------------------------------------
    @property
    def is_super_admin(self):
        return bool(self.role_id and self.role.is_super_admin)

    def get_permission_keys(self):
        """Ensemble des permissions effectives (`{'*'}` pour le Super Admin). Mis en cache par instance."""
        if not hasattr(self, "_permission_keys"):
            if self.is_super_admin:
                self._permission_keys = {"*"}
            else:
                self._permission_keys = set(self.role.permissions.values_list("codename", flat=True))
        return self._permission_keys

    def has_permission_key(self, key):
        keys = self.get_permission_keys()
        return "*" in keys or key in keys

    # -- compatibilité Django admin (réservé aux Super Admins) ----------------
    @property
    def is_staff(self):
        return self.is_active and self.is_super_admin

    @property
    def is_superuser(self):
        return self.is_active and self.is_super_admin

    def has_perm(self, perm, obj=None):
        return self.is_superuser

    def has_module_perms(self, app_label):
        return self.is_superuser

    # -- verrouillage après échecs de connexion ------------------------------
    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def register_failed_login(self):
        type(self).objects.filter(pk=self.pk).update(failed_login_count=F("failed_login_count") + 1)
        self.refresh_from_db(fields=["failed_login_count"])
        if self.failed_login_count >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            self.locked_until = timezone.now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            self.failed_login_count = 0
            self.save(update_fields=["locked_until", "failed_login_count", "updated_at"])

    def register_successful_login(self):
        self.failed_login_count = 0
        self.locked_until = None
        self.last_login = timezone.now()
        self.save(update_fields=["failed_login_count", "locked_until", "last_login", "updated_at"])
