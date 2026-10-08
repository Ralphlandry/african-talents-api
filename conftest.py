import pytest
from django.core.cache import cache
from django.utils.text import slugify
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.models import Permission, Role, User
from apps.accounts.rbac import sync_rbac

PASSWORD = "Str0ng-Pass-123!"


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()


@pytest.fixture(autouse=True)
def _rbac(request):
    """Synchronise le catalogue de permissions pour les tests qui utilisent la base."""
    if request.node.get_closest_marker("django_db") or "db" in request.fixturenames:
        request.getfixturevalue("db")
        sync_rbac()


@pytest.fixture
def password():
    return PASSWORD


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def make_role(db):
    def _make(name, perms=(), **kwargs):
        role = Role.objects.create(name=name, slug=slugify(name), **kwargs)
        role.permissions.set(Permission.objects.filter(codename__in=perms))
        return role

    return _make


@pytest.fixture
def make_user(db):
    def _make(email, role, password=PASSWORD, **kwargs):
        kwargs.setdefault("full_name", "Test User")
        return User.objects.create_user(email=email, password=password, role=role, **kwargs)

    return _make


@pytest.fixture
def super_role(db):
    return Role.objects.get(slug="super_admin")


@pytest.fixture
def super_admin(make_user, super_role):
    return make_user("boss@example.com", super_role, full_name="Boss")


@pytest.fixture
def auth_client():
    def _auth(user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
        return client

    return _auth


@pytest.fixture
def make_competition(db):
    from apps.competition.models import Competition

    def _make(name="Saison Test", is_current=True, status=Competition.ACTIVE, **kwargs):
        from django.utils.text import slugify

        return Competition.objects.create(
            name=name, slug=slugify(name), start_date="2026-01-01", end_date="2026-12-31",
            status=status, is_current=is_current, **kwargs,
        )

    return _make


@pytest.fixture
def make_category(db):
    from apps.categories.models import Category

    def _make(name="Musique", competition=None, status=Category.PUBLISHED, **kwargs):
        from django.utils.text import slugify

        return Category.objects.create(name=name, slug=slugify(name), competition=competition, status=status, order=1, **kwargs)

    return _make


@pytest.fixture
def make_candidate(db):
    from apps.candidates.models import Candidate

    def _make(competition, category, code="AT-001", first_name="Jean", last_name="Dupont", **kwargs):
        from django.utils.text import slugify

        kwargs.setdefault("status", Candidate.PUBLISHED)
        kwargs.setdefault("is_active", True)
        return Candidate.objects.create(
            competition=competition, category=category, code=code, first_name=first_name, last_name=last_name,
            slug=slugify(f"{first_name}-{last_name}-{code}"), **kwargs,
        )

    return _make


@pytest.fixture
def make_vote_package(db):
    from apps.voting.models import VotePackage

    def _make(competition, quantity=10, price_xaf=1000, is_active=True, **kwargs):
        return VotePackage.objects.create(
            competition=competition, label=kwargs.pop("label", f"{quantity} votes"), quantity=quantity,
            price_xaf=price_xaf, is_active=is_active, **kwargs,
        )

    return _make


@pytest.fixture
def make_vote_order(db):
    from apps.voting.models import VoteOrder

    def _make(candidate, vote_package, status=VoteOrder.PENDING, idempotency_key=None, **kwargs):
        import uuid

        return VoteOrder.objects.create(
            candidate=candidate, vote_package=vote_package, quantity=vote_package.quantity,
            amount_xaf=vote_package.price_xaf, customer_phone="+237655500001", operator="MTN",
            status=status, idempotency_key=idempotency_key or str(uuid.uuid4()), **kwargs,
        )

    return _make


@pytest.fixture
def make_payment(db):
    from apps.payments.models import Payment

    def _make(order, status=Payment.PENDING, **kwargs):
        return Payment.objects.create(
            vote_order=order, reference=order.order_number, environment="test",
            amount_xaf=order.amount_xaf, phone=order.customer_phone, operator=order.operator,
            status=status, **kwargs,
        )

    return _make


@pytest.fixture
def uploaded_image():
    """Fausse image JPEG minimale valide (signature de fichier correcte, pour les tests d'upload)."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    jpeg_bytes = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")

    def _make(name="photo.jpg"):
        return SimpleUploadedFile(name, jpeg_bytes, content_type="image/jpeg")

    return _make
