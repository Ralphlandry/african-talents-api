from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    FailedVotePaymentCompensationView,
    RankingView,
    VoteAdjustView,
    VoteListView,
    VotePackageViewSet,
    VotesByCategoryView,
    VotesSeriesView,
)

router = SimpleRouter()
router.register("vote-packages", VotePackageViewSet, basename="vote-package")
router.register("votes", VoteListView, basename="vote")

urlpatterns = [
    # ordre important : ces routes explicites doivent être évaluées avant "votes/<pk>/" du router
    path("votes/adjust/", VoteAdjustView.as_view(), name="votes-adjust"),
    path(
        "votes/compensate-failed-payment/",
        FailedVotePaymentCompensationView.as_view(),
        name="votes-compensate-failed-payment",
    ),
    path("votes/by-category/", VotesByCategoryView.as_view(), name="votes-by-category"),
    path("votes/series/", VotesSeriesView.as_view(), name="votes-series"),
    path("rankings/", RankingView.as_view(), name="rankings"),
    *router.urls,
]
