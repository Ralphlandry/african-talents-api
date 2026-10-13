import pytest
from django.urls import get_resolver

from apps.core.permissions import DenyByDefault, RBACPermission


@pytest.mark.django_db
def test_health_ok(api):
    response = api.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_unknown_url_returns_json_404(api):
    response = api.get("/api/v1/does-not-exist/")
    assert response.status_code == 404
    assert response["Content-Type"].startswith("application/json")
    assert response.json()["code"] == "NOT_FOUND"


@pytest.mark.django_db
def test_unauthenticated_admin_route_is_401_with_standard_format(api):
    response = api.get("/api/v1/admins/")
    assert response.status_code == 401
    body = response.json()
    assert body["success"] is False and body["code"] == "NOT_AUTHENTICATED"


def _iter_patterns(patterns, prefix=""):
    for p in patterns:
        route = prefix + str(p.pattern)
        if hasattr(p, "url_patterns"):
            yield from _iter_patterns(p.url_patterns, route)
        else:
            yield route, p.callback


@pytest.mark.django_db
def test_every_api_route_declares_explicit_permissions():
    """Garde-fou « refus par défaut » : aucune route /api/v1 ne peut reposer sur la permission par défaut."""
    checked = 0
    for route, callback in _iter_patterns(get_resolver().url_patterns):
        if not route.startswith("api/v1/"):
            continue
        view_class = getattr(callback, "cls", None)
        if view_class is None:
            continue
        checked += 1
        assert view_class.permission_classes != [DenyByDefault], f"{route} n'a pas de permission explicite"
        if RBACPermission in view_class.permission_classes:
            assert getattr(view_class, "permission_map", None), f"{route} : permission_map manquante"
    assert checked > 5
