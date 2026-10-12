from django.urls import path

from . import views

urlpatterns = [
    path("competition/", views.CurrentCompetitionView.as_view(), name="public-competition"),
    path("categories/", views.PublicCategoryListView.as_view(), name="public-categories"),
    path("candidates/", views.PublicCandidateListView.as_view(), name="public-candidates"),
    path("candidates/<slug:slug>/", views.PublicCandidateDetailView.as_view(), name="public-candidate-detail"),
    path("news/", views.PublicNewsListView.as_view(), name="public-news"),
    path("news/<slug:slug>/", views.PublicNewsDetailView.as_view(), name="public-news-detail"),
    path("team/", views.PublicTeamListView.as_view(), name="public-team"),
    path("partners/", views.PublicPartnerListView.as_view(), name="public-partners"),
    path("site/", views.PublicSiteSettingsView.as_view(), name="public-site-settings"),
    path("rankings/", views.PublicRankingView.as_view(), name="public-rankings"),
    path("vote-packages/", views.PublicVotePackageListView.as_view(), name="public-vote-packages"),
    path("payment-methods/", views.PublicPaymentMethodsView.as_view(), name="public-payment-methods"),
    path("vote-orders/", views.PublicVoteOrderCreateView.as_view(), name="public-vote-order-create"),
    path("vote-orders/<str:order_number>/", views.PublicVoteOrderStatusView.as_view(), name="public-vote-order-status"),
]
