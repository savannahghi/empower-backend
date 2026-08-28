"""Settings URLs."""
from django.urls import path

from sil_advantage.settings import views

urlpatterns = [
    path(
        "org_settings/",
        views.OrganisationSettingsView.as_view(),
        name="org_settings",
    ),
    path(
        "branch_settings/",
        views.BranchSettingsView.as_view(),
        name="branch_settings",
    ),
]
