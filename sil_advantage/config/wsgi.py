"""WSGI app configuration."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE",
    "sil_advantage.config.settings",
)

application = get_wsgi_application()
