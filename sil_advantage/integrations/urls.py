"""Integrations URLs."""
from django.urls import path

from sil_advantage.integrations.files.google_drive import GoogleDriveWebhook

urlpatterns = (
    path(
        "google-drive/",
        GoogleDriveWebhook.as_view(),
        name="google-drive",
    ),
)
