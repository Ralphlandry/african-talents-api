"""
Scénario de bout en bout : un Super Admin configure une compétition complète, un
visiteur public vote et est crédité via un paiement confirmé par webhook, puis
l'admin retrouve ce paiement dans ses écrans finance et son journal d'audit.

Ce test ne remplace pas les tests unitaires/service de chaque app (bien plus
nombreux ailleurs) : il vérifie que les pièces s'assemblent correctement entre
elles, comme le ferait une vraie utilisation du produit.
"""
import json

import pytest


class FakeGatewayClient:
    """Faux client HR-Skills Pay partagé par tout le scénario (aucun appel réseau réel)."""

    def __init__(self):
        self.last_status_check = None

    def create_mobile_money_payin(self, **kwargs):
        return {"status": "PENDING", "provider_reference": "HRS-E2E-1", "fees_xaf": None, "net_amount_xaf": None}

    def get_payment_status(self, reference):
        self.last_status_check = reference
        return {"status": "SUCCESS", "amount_xaf": self.amount, "fees_xaf": 30, "net_amount_xaf": self.amount - 30}


def sign(body: bytes, secret: str) -> str:
    import hashlib
    import hmac

    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.mark.django_db
def test_full_platform_flow(api, auth_client, super_admin, password, settings, monkeypatch):
    from apps.audit.models import AuditLog
    from apps.payments import services as payment_services

    settings.HRSKILLS_WEBHOOK_SECRET = "whsec_e2e"
    fake_gateway = FakeGatewayClient()
    monkeypatch.setattr(payment_services, "build_client_from_settings", lambda: fake_gateway)

    admin = auth_client(super_admin)

    # 1. Connexion (déjà couverte ailleurs en détail ; ici on vérifie juste qu'elle ouvre le reste du parcours)
    login = api.post("/api/v1/auth/login/", {"email": super_admin.email, "password": password}, format="json")
    assert login.status_code == 200

    # 2. Compétition + phase active + votes ouverts
    competition_resp = admin.post("/api/v1/competitions/", {
        "name": "Saison E2E", "start_date": "2026-01-01", "end_date": "2026-12-31",
    }, format="json")
    assert competition_resp.status_code == 201
    competition_id = competition_resp.json()["id"]
    assert admin.post(f"/api/v1/competitions/{competition_id}/start/").status_code == 200
    assert admin.post(f"/api/v1/competitions/{competition_id}/toggle-votes/").status_code == 200
    phase_resp = admin.post(f"/api/v1/competitions/{competition_id}/phases/", {
        "name": "Votes", "start_date": "2026-01-01", "end_date": "2026-12-31", "status": "active",
    }, format="json")
    assert phase_resp.status_code == 201

    # 3. Catégorie publiée
    category_resp = admin.post("/api/v1/categories/", {"competition": competition_id, "name": "Musique"}, format="json")
    category_id = category_resp.json()["id"]
    assert admin.post(f"/api/v1/categories/{category_id}/publish/").status_code == 200

    # 4. Candidat publié et actif
    candidate_resp = admin.post("/api/v1/candidates/", {
        "competition": competition_id, "category": category_id, "code": "at-e2e",
        "first_name": "Aminata", "last_name": "Diallo", "city": "Conakry",
    }, format="json")
    assert candidate_resp.status_code == 201
    candidate_id = candidate_resp.json()["id"]
    candidate_slug = candidate_resp.json()["slug"]
    assert admin.post(f"/api/v1/candidates/{candidate_id}/publish/").status_code == 200
    assert admin.post(f"/api/v1/candidates/{candidate_id}/activate/").status_code == 200

    # 5. Forfait de vote défini par l'admin (décision B)
    package_resp = admin.post("/api/v1/vote-packages/", {
        "competition": competition_id, "label": "10 votes", "quantity": 10, "price_xaf": 1000,
    }, format="json")
    assert package_resp.status_code == 201
    package_id = package_resp.json()["id"]
    fake_gateway.amount = 1000

    # 6. Le site public voit déjà tout ce qui vient d'être créé
    assert api.get("/api/v1/public/competition/").json()["name"] == "Saison E2E"
    assert any(c["slug"] == category_resp.json()["slug"] for c in api.get("/api/v1/public/categories/").json())
    public_candidates = api.get("/api/v1/public/candidates/").json()["results"]
    assert any(c["code"] == "AT-E2E" for c in public_candidates)
    public_packages = api.get("/api/v1/public/vote-packages/").json()
    assert public_packages[0]["price_xaf"] == 1000

    # 7. Un visiteur vote : commande + paiement initié
    order_resp = api.post("/api/v1/public/vote-orders/", {
        "candidate": candidate_slug, "vote_package": package_id, "phone": "+237655500001",
        "operator": "MTN", "idempotency_key": "e2e-vote-1", "accept_terms": True,
    }, format="json")
    assert order_resp.status_code == 201, order_resp.json()
    order_number = order_resp.json()["order_number"]
    assert order_resp.json()["status"] == "PENDING"

    # 8. HR-Skills Pay confirme par webhook — revérifié avant tout crédit de vote
    body = json.dumps({"reference": order_number, "status": "SUCCESS", "event_type": "payment.succeeded"})
    webhook_resp = api.post(
        "/api/v1/payments/webhooks/hrskills/", data=body, content_type="application/json",
        HTTP_X_HUB_SIGNATURE=sign(body.encode(), "whsec_e2e"),
    )
    assert webhook_resp.status_code == 200
    assert fake_gateway.last_status_check == order_number  # la revérification a bien eu lieu

    # 9. Le visiteur voit sa commande payée en interrogeant le statut
    status_resp = api.get(f"/api/v1/public/vote-orders/{order_number}/")
    assert status_resp.json()["status"] == "PAID"

    # 10. Le classement public ET admin reflètent les 10 votes crédités
    public_ranking = api.get("/api/v1/public/rankings/").json()
    assert public_ranking[0]["code"] == "AT-E2E" and public_ranking[0]["votes_total"] == 10
    admin_ranking = admin.get("/api/v1/rankings/").json()
    assert admin_ranking[0]["votes_total"] == 10
    candidate_detail = api.get(f"/api/v1/public/candidates/{candidate_slug}/").json()
    assert candidate_detail["votes_total"] == 10 and candidate_detail["rank"] == 1

    # 11. La finance admin voit ce paiement
    overview = admin.get("/api/v1/finance/overview/").json()
    assert overview["total_collected_xaf"] == 1000 and overview["successful_payments"] == 1
    transactions = admin.get("/api/v1/payments/").json()
    assert transactions["results"][0]["reference"] == order_number
    assert transactions["results"][0]["status"] == "SUCCESS"

    # 12. Actualité publiée, visible publiquement
    news_resp = admin.post("/api/v1/news/", {"title": "La saison E2E est lancée"}, format="json")
    news_id = news_resp.json()["id"]
    assert admin.post(f"/api/v1/news/{news_id}/publish/").status_code == 200
    public_news = api.get("/api/v1/public/news/").json()["results"]
    assert any(n["title"] == "La saison E2E est lancée" for n in public_news)

    # 13. Équipe, visible publiquement
    admin.post("/api/v1/team/", {"type": "coach", "full_name": "Coach E2E"}, format="json")
    assert any(m["full_name"] == "Coach E2E" for m in api.get("/api/v1/public/team/").json())

    # 14. Le journal d'audit a bien enregistré les actions clés de tout ce parcours
    actions = set(AuditLog.objects.values_list("action", flat=True))
    assert {
        "ADMIN_LOGIN", "COMPETITION_UPDATED", "COMPETITION_STARTED", "CATEGORY_CREATED",
        "CATEGORY_PUBLISHED", "CANDIDATE_CREATED", "CANDIDATE_PUBLISHED", "VOTE_PACKAGE_CREATED",
        "VOTE_ORDER_CREATED", "PAYMENT_INITIATED", "PAYMENT_WEBHOOK_RECEIVED", "PAYMENT_STATUS_CHANGED",
        "NEWS_CREATED", "NEWS_PUBLISHED", "TEAM_MEMBER_CREATED",
    }.issubset(actions)


@pytest.mark.django_db
def test_permission_boundaries_hold_across_the_whole_flow(auth_client, make_role, make_user, make_competition, make_category, make_candidate):
    """Un admin Contenu (actualités uniquement) ne doit toucher ni aux candidats ni aux finances, nulle part."""
    competition = make_competition()
    category = make_category(competition=competition)
    candidate = make_candidate(competition, category)

    content_admin = make_user("content@example.com", make_role("Contenu", ["news.view", "news.create"]))
    client = auth_client(content_admin)

    assert client.get("/api/v1/candidates/").status_code == 403
    assert client.post(f"/api/v1/candidates/{candidate.pk}/publish/").status_code == 403
    assert client.get("/api/v1/finance/overview/").status_code == 403
    assert client.get("/api/v1/payments/").status_code == 403
    assert client.post("/api/v1/votes/adjust/", {"candidate": str(candidate.pk), "delta": 5, "reason": "test"}, format="json").status_code == 403
    assert client.get("/api/v1/admins/").status_code == 403
    # mais ce pour quoi il a une permission fonctionne bien
    assert client.post("/api/v1/news/", {"title": "Autorisé"}, format="json").status_code == 201
