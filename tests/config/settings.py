# flake8: noqa

import logging
import os
import tempfile

from sil_advantage.config.settings import *

ENVIRONMENT = "test"

os.environ["CHARGE_MASTER_HOST"] = "https://chargemaster.example.invalid/v1"
os.environ[
    "CHARGE_MASTER_TOKEN_URL"
] = "https://chargemaster.example.invalid/oauth2/token/"
os.environ["CHARGE_MASTER_CLIENT_ID"] = "qJ2InNS67k6q4CutdEvU1Amt9hgheqhGPMoxgAu2"
os.environ[
    "CHARGE_MASTER_CLIENT_SECRET"
] = "ssJxoX8SqASOSn8YxMoQG9OS0VgExZRGoNbzLMdhCwLFSe7F9pg8f5EVMNthdvsROOpdv05Jz2GUV5eFKrmCA0KyzXa1JZ8YoqzJFhj04lflAwNNoeCR86sQSIHm1SxD"
os.environ["CHARGE_MASTER_USERNAME"] = "integration@example.invalid"
os.environ["CHARGE_MASTER_PASSWORD"] = "yulemsee"
os.environ["CHARGE_MASTER_GRANT_TYPE"] = "password"

TEST_APPS = (
    "tests.common.test_app",
    "tests.common.sample_app",
)
INSTALLED_APPS += TEST_APPS
REST_FRAMEWORK.update(
    {
        "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
        "DEFAULT_PERMISSION_CLASSES": (
            "sil_advantage.sil_auth.permission_classes.OrganisationIsActive",
        ),
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES": [],
        "TEST_REQUEST_DEFAULT_FORMAT": "json",
        "TEST_REQUEST_RENDERER_CLASSES": (
            "rest_framework.renderers.JSONRenderer",
            "rest_framework.renderers.MultiPartRenderer",
        ),
    }
)

# Test optimizations
# We have not disabled logging - some tests verify logs
DEBUG = False
TEMPLATE_DEBUG = False
LOGGING["handlers"]["syslog"] = LOGGING["handlers"]["console"]
LOGGER = logging.getLogger(__name__)

# Use fewer iterations when making passwords in tests
# We still use PBKDF because the 'change password' behavior depends on it
PASSWORD_HASHERS = ("tests.test_password_hasher.PBKDF2PasswordHasher",)

# disable database migrations when testing
MIGRATION_MODULES = {
    local_app: None for local_app in [app.split(".")[1] for app in LOCAL_APPS]
}
MIGRATION_MODULES.update(
    {
        other_app: None
        for other_app in [
            app.split(".")[-1] for app in set(INSTALLED_APPS) - set(LOCAL_APPS)
        ]
    }
)
MIGRATION_MODULES.update({"test_app": None})
LOGGER.debug(
    "Migration modules: %(migration_module)s",
    migration_modules=MIGRATION_MODULES,
)

MEDIA_ROOT = tempfile.mkdtemp()
STORAGES = {
    **STORAGES,
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
MAX_IMAGE_HEIGHT = 2_000  # pixels
MAX_IMAGE_WIDTH = 2_000  # pixels

AUTHENTICATION_BACKENDS = ("django.contrib.auth.backends.ModelBackend",)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "storyline-fever",
    },
}
SIL_CACHEABLE_ENABLED = True
SIL_CACHEABLE_TTL = 60 * 60

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "slade_emr_poc"),
        "USER": os.getenv("DB_USER", "app"),
        "PASSWORD": os.getenv("DB_PASS", "app"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {
            "isolation_level": IsolationLevel.READ_COMMITTED,
        },
    }
}

SYNC_WITH_ERP = False
SYNC_WITH_HEALTH_CRM = False
SYNC_WITH_CLINICAL_SERVICE = False
CELERY_ALWAYS_EAGER = True
