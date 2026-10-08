from django.urls import path

from .views import HealthView, SiteSettingsView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("settings/", SiteSettingsView.as_view(), name="site-settings"),
]
