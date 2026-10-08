"""Routes de l'API v1. Chaque jalon ajoute ses applications ici."""
from django.urls import include, path

urlpatterns = [
    path("", include("apps.core.urls")),
    path("auth/", include("apps.accounts.urls_auth")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.audit.urls")),
    # --- jalon 2 : contenu (espace administrateur) ---
    path("", include("apps.competition.urls")),
    path("", include("apps.categories.urls")),
    path("", include("apps.candidates.urls")),
    path("", include("apps.news.urls")),
    path("", include("apps.team.urls")),
    path("", include("apps.partners.urls")),
    path("", include("apps.media.urls")),
    # --- jalon 3 : forfaits de vote, votes, paiements, finance (espace administrateur) ---
    path("", include("apps.voting.urls")),
    path("", include("apps.payments.urls")),
    path("", include("apps.finance.urls")),
    # --- API publique, en lecture seule sauf création de commande de vote, sans authentification admin ---
    path("public/", include("apps.publicapi.urls")),
]
