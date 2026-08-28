"""Settings app."""
from django.apps import AppConfig


class SettingsConfig(AppConfig):
    """Settings app configuration."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "sil_advantage.settings"
