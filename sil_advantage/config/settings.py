"""Advantage Backend Settings."""

import logging.config
import os
from socket import gethostbyname, gethostname

import sentry_sdk
from corsheaders.defaults import default_headers
from django.db.backends.postgresql.psycopg_any import IsolationLevel
from django.utils.translation import gettext_lazy as _
from google.oauth2 import service_account
from kombu import Exchange, Queue
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.redis import RedisIntegration

from sil_advantage import __version__
from sil_advantage.config.utils import get_bool_env, split_env_values

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

""" Deployment """
ENVIRONMENT = os.getenv("ENVIRONMENT", "test").lower()
DEBUG = ENVIRONMENT in ("test", "dev")

SECRET_KEY = os.getenv(
    "SECRET_KEY",
    "asrbrih1m@^74lpy&e+7#m!4+2o0tetybz6-r9i%gask%lvv#!",
)

allowed_hosts = os.getenv(
    "ALLOWED_HOSTS",
    ".localhost,127.0.0.1,"
    f".slade360edi.com,.slade360.co.ke,{gethostbyname(gethostname())}",
)
ALLOWED_HOSTS = allowed_hosts.split(",")
API_HOST = os.getenv("API_HOST", "http://localhost:8000")
API_USER_AGENT = os.getenv("API_USER_AGENT", "Advantage Backend")
ADVANTAGE_FRONTEND_URL = os.getenv(
    "ADVANTAGE_FRONTEND_URL",
    "http://localhost:4200",
)

CORS_ALLOWED_ORIGIN_REGEXES = (
    r"^(https?://)?(.+)-?.slade360\.co.ke$",
    r"^(https?://)?(.+)-?.slade360\.com$",
    r"^(https?://)?(.+)-?.healthcloud\.co.ke$",
    r"^(https?://)?(.+)-?.slade360edi\.com$",
    r"^(https?://)?(.+)-?.savannahghi\.org$",
    r"^(https?://)?(.+)-?.bewell\.co.ke$",
    r"^(https?://)?(.+)-?.tiberbu\.health$",
    os.getenv("CORS_ORIGIN", ""),
)

CORS_ALLOWED_ORIGINS = [
    "https://advantage.slade360.com",
    "https://uat-emr.advantage.slade360.com",
    "https://staging-emr.advantage.slade360.com",
    "http://localhost:4200",
    "http://127.0.0.1:4200",
    "https://review-advantage.web.app",
    "https://review-empower.web.app",
    "https://prod-empower.web.app",
    "https://staging-empower.web.app",
]
CORS_ALLOW_HEADERS = list(default_headers) + [
    "X-Workstation",
    "X-Department",
    "X-Branch",
    "X-Cluster",
    "X-Variant",
]

""" Apps """
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.humanize",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "django_extensions",
    "sil_renderers",
    "phonenumber_field",
    "mjml",
    "drf_yasg",
    "sil_backup_utils",
    "django_celery_beat",
    "modeltranslation",
    "behave_django",
]
LOCAL_APPS = [
    "sil_advantage.sil_auth",
    "sil_advantage.billing",
    "sil_advantage.common",
    "sil_advantage.permissions",
    "sil_advantage.patients",
    "sil_advantage.practitioners",
    "sil_advantage.scheduling",
    "sil_advantage.notifications",
    "sil_advantage.visits",
    "sil_advantage.settings",
    "sil_advantage.integrations",
    "sil_advantage.segments",
    "sil_advantage.prescriptions",
]
INSTALLED_APPS += LOCAL_APPS
if ENVIRONMENT == "dev":
    INSTALLED_APPS.append("silk")
    SILKY_PYTHON_PROFILER = True
    SILKY_ANALYZE_QUERIES = True
    SILKY_PYTHON_PROFILER_BINARY = True
    SILKY_PYTHON_PROFILER_RESULT_PATH = "profiling/"
    SILKY_EXPLAIN_FLAGS = {"costs": True, "verbose": True}

""" Middleware """
MIDDLEWARE: list[str] = ["compression_middleware.middleware.CompressionMiddleware"]
if ENVIRONMENT == "dev":
    MIDDLEWARE.append("silk.middleware.SilkyMiddleware")

MIDDLEWARE += [
    "sil_advantage.common.middleware.LatencyMiddleware",
    "sil_sentry_middleware.sentry_middleware_for_4xx",
    "sil_sentry_middleware.sentry_middleware_for_5xx",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_PROXY_SSL_HEADER = (
    os.getenv("SECURE_PROXY_SSL_HEADER", "HTTP_X_FORWARDED_PROTO"),
    "https",
)
SECURE_BROWSER_XSS_FILTER = True

SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

CSRF_COOKIE_AGE = None
CSRF_COOKIE_HTTPONLY = True

""" Cache """
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.getenv("REDIS_DB_URL"),
        "KEY_PREFIX": f"advantage.{ENVIRONMENT}.",
    },
}
SIL_CACHEABLE_ENABLED = get_bool_env("SIL_CACHEABLE_ENABLED")
SIL_CACHEABLE_TTL = int(os.getenv("SIL_CACHEABLE_TTL", 21600))
VISIT_ASYNC_ENABLED = get_bool_env("VISIT_ASYNC_ENABLED", "False")

""" Django Rest Framework """
REST_FRAMEWORK = {
    "DEFAULT_MODEL_SERIALIZER_CLASS": ("rest_framework.serializers.ModelSerializer",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.OrderingFilter",
        "rest_framework.filters.SearchFilter",
        "sil_advantage.common.filters.OrgUnitFilterBackend",
    ),
    "DEFAULT_PARSER_CLASSES": (
        "drf_orjson_renderer.parsers.ORJSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FileUploadParser",
    ),
    "DEFAULT_RENDERER_CLASSES": [
        "drf_orjson_renderer.renderers.ORJSONRenderer",
        "sil_renderers.PDFRenderer",
        "sil_renderers.ExcelRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "sil_advantage.sil_auth.keycloak.KeycloakAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_METADATA_CLASS": "rest_framework.metadata.SimpleMetadata",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "user": "100/second",
        "anon": "4/minute",
        "lenient_anon": "20/minute",
    },
    "DEFAULT_PAGINATION_CLASS": (
        "sil_advantage.common.utilities.paginator.SILPagingSerializer"
    ),
    "PAGE_SIZE": 50,
    "DATETIME_FORMAT": "iso-8601",
    "DATE_FORMAT": "iso-8601",
    "TIME_FORMAT": "iso-8601",
    "EXCEPTION_HANDLER": (
        "sil_custom_exception_handler.handler.custom_exception_handler"
    ),
    "COERCE_DECIMAL_TO_STRING": False,
}

FILTERS_STRICTNESS = "STRICTNESS.RAISE_VALIDATION_ERROR"

""" Django Templates """
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR + "/templates/"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.debug",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]
MJML_BACKEND_MODE = "cmd"
MJML_EXEC_CMD = os.getenv("MJML_EXEC_CMD", "node_modules/.bin/mjml")
# django-mjml shells out to the mjml binary on every django.setup() and raises
# ImproperlyConfigured if it is absent. node_modules is not part of this repo,
# so a clean clone cannot run any management command without this switch.
MJML_CHECK_CMD_ON_STARTUP = get_bool_env("MJML_CHECK_CMD_ON_STARTUP", "False")

""" Auth """
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation."
        "UserAttributeSimilarityValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation." "MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation." "CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation." "NumericPasswordValidator",
    },
]
OLD_PASSWORD_FIELD_ENABLED = True
KEYCLOAK = {
    "BASE_URL": os.getenv("KEYCLOAK_BASE_URL", "http://localhost:8081"),
    "REALM": os.getenv("KEYCLOAK_REALM", "empower"),
    "CLIENT_ID": os.getenv("KEYCLOAK_CLIENT_ID", ""),
    "CLIENT_SECRET": os.getenv("KEYCLOAK_CLIENT_SECRET", ""),
    "TIMEOUT": int(os.getenv("KEYCLOAK_TIMEOUT", "10")),
    # Keycloak has no notion of a Slade code. A token may carry one as a
    # `business_partner` claim; otherwise all users map to this organisation.
    "DEFAULT_SLADE_CODE": os.getenv("KEYCLOAK_DEFAULT_SLADE_CODE", ""),
}
KEYCLOAK["TOKEN_URL"] = (
    f"{KEYCLOAK['BASE_URL']}/realms/{KEYCLOAK['REALM']}"
    "/protocol/openid-connect/token"
)
KEYCLOAK["INTROSPECTION_URL"] = (
    f"{KEYCLOAK['BASE_URL']}/realms/{KEYCLOAK['REALM']}"
    "/protocol/openid-connect/token/introspect"
)

LOGIN_REDIRECT_URL = "/"
AUTHENTICATION_BACKENDS = ("django.contrib.auth.backends.ModelBackend",)
AUTH_USER_MODEL = "sil_auth.SILUser"

# Outbound clients for user provisioning and HealthCRM. Neither is part of
# Empower; these settings exist so the modules that import them still load.
SIL_AUTH_SERVER_DOMAIN = os.getenv("AUTHSERVER_DOMAIN", "http://localhost:9000")
AUTH_SERVER_API_SCOPES = ["auth.me.read", "auth.user.read", "advantage.*"]

AUTH_SERVER_API_CONNECTION = {
    "HOST": os.getenv(
        "AUTH_SERVER_API_HOST",
        "authserver.healthcloud.co.ke",
    ),
    "SCHEME": os.getenv("AUTH_SERVER_API_SCHEME", "https"),
    "DOMAIN": SIL_AUTH_SERVER_DOMAIN,
    "KEY": os.getenv("AUTHSERVER_API_CLIENT_ID", ""),
    "SECRET": os.getenv("AUTHSERVER_CLIENT_SECRET", ""),
    "USER_EMAIL": os.getenv("USER_EMAIL", "network.admin@slade360.co.ke"),
    "USER_PASSWORD": os.getenv("USER_PASSWORD", ""),
    "TOKEN_URL": os.getenv(
        "AUTH_SERVER_API_TOKEN_URL",
        "{}/oauth2/token/".format(SIL_AUTH_SERVER_DOMAIN),
    ),
    "SCOPES": AUTH_SERVER_API_SCOPES,
}

""" Miscellaneous """
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

LANGUAGES = [("en", _("English")), ("fr", _("French")), ("sw", _("Swahili"))]

# Model translations settings
MODELTRANSLATION_DEFAULT_LANGUAGE = "en"
MODELTRANSLATION_ENABLE_FALLBACKS = False

LOCALE_PATHS = [
    os.path.join(BASE_DIR, "locale"),
]

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

DECIMAL_PLACES = 4  # Decimal places to use for all decimal values

""" Media """
ROOT_URLCONF = "sil_advantage.config.urls"
STATIC_ROOT = os.getenv("STATIC_ROOT", os.path.join(BASE_DIR, "static"))
STATIC_URL = "/static/"
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.gcloud.GoogleCloudStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}
MEDIA_URL = "/media/"

GS_BUCKET_NAME = os.getenv("GS_BUCKET_NAME", "sil-advantage-test")
GS_CREDENTIALS = ""
GOOGLE_APPLICATION_CREDENTIALS = os.getenv(
    "GOOGLE_APPLICATION_CREDENTIALS",
    "",
)
if GOOGLE_APPLICATION_CREDENTIALS:
    GS_CREDENTIALS = service_account.Credentials.from_service_account_file(
        GOOGLE_APPLICATION_CREDENTIALS
    )
GCS_ROOT = "https://storage.googleapis.com/{bucket_name}/".format(
    bucket_name=GS_BUCKET_NAME
)

MEDIA_PREFIX = "media"
MEDIA_URL = "{gcs_root}{prefix}/".format(
    gcs_root=GCS_ROOT,
    prefix=MEDIA_PREFIX,
)

MAX_IMAGE_HEIGHT = 10_800  # pixels
MAX_IMAGE_WIDTH = 10_800  # pixels
MAX_UPLOAD_SIZE = 20_971_520  # 20 MB
FILE_UPLOAD_CHUNK_SIZE = 2_097_152  # 2 MB

""" Database """
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "slade_emr_poc"),
        "USER": os.getenv("DB_USER", "app"),
        "PASSWORD": os.getenv("DB_PASS", "app"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "CONN_HEALTH_CHECKS": True,
        "DISABLE_SERVER_SIDE_CURSORS": True,
        "OPTIONS": {
            "isolation_level": IsolationLevel.READ_COMMITTED,
        },
    }
}

API_USER_AGENTS = {"Advantage Backend"}

# Database backup settings
MONITORING_EMAIL_RECIPIENT = os.getenv(
    "ADVANTAGE_GROUP_EMAIL",
    "advantage@savannahinformatics.com",
)

""" Logging """
LOGGING = {
    "version": 1,
    "disable_existing_loggers": True,
    "filters": {
        "require_debug_false": {
            "()": "django.utils.log.RequireDebugFalse",
        },
    },
    "formatters": {
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s [%(name)s:%(lineno)s] "
            + "%(module)s %(process)d %(thread)d %(message)s",
            "datefmt": "%d/%b/%Y %H:%M:%S",
        },
        "simple": {"format": "%(levelname)s %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG" if DEBUG else "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "propagate": True,
            "level": "INFO" if DEBUG else "ERROR",
            "name": ENVIRONMENT,
        },
        "django.request": {
            "handlers": ["console"],
            "propagate": True,
            "level": "INFO" if DEBUG else "ERROR",
            "name": ENVIRONMENT,
            "filters": ["require_debug_false"],
        },
        "django.db": {
            "handlers": ["console"],
            "propagate": True,
            "level": "INFO" if DEBUG else "ERROR",
            "name": ENVIRONMENT,
        },
        "django.db.backends": {
            "handlers": ["console"],
            "propagate": True,
            "level": "INFO" if DEBUG else "ERROR",
            "name": ENVIRONMENT,
        },
        "sil": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "name": ENVIRONMENT,
        },
        "sentry.errors": {
            "level": "INFO" if DEBUG else "ERROR",
            "handlers": ["console"],
            "propagate": False,
        },
        "": {
            "handlers": ["console"],
            "level": "INFO" if DEBUG else "ERROR",
            "name": ENVIRONMENT,
            "propagate": True,
        },
    },
}
LOGGING_CONFIG = None
logging.config.dictConfig(LOGGING)

""" Sentry """
sentry_sdk.init(  # type: ignore
    dsn=os.getenv("RAVEN_DSN"),
    environment=ENVIRONMENT,
    release=__version__,
    integrations=[
        CeleryIntegration(),
        DjangoIntegration(),
        RedisIntegration(),
        LoggingIntegration(event_level=logging.ERROR),
    ],
    send_default_pii=get_bool_env("SENTRY_COLLECT_DEFAULT_PII"),
    traces_sample_rate=1.0,
)
RAVEN_CONFIG = {"dsn": os.getenv("RAVEN_DSN")}

""" Email """
SERVER_EMAIL = "no-reply@healthcloud.co.ke"
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL")
SYSTEM_ADMIN_EMAIL = os.getenv("USER_EMAIL", "network.admin@slade360.co.ke")
OUTGOING_EMAIL_SOURCE = DEFAULT_FROM_EMAIL
EMAIL_BACKEND = "django_ses.SESBackend"
AWS_ACCESS_KEY_ID = os.environ.get("AWS_KEY_ID", None)
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET", None)
ADVANTAGE_GROUP_EMAIL = os.getenv(
    "ADVANTAGE_GROUP_EMAIL",
    "advantage@savannahinformatics.com",
)
GTM_GROUP_EMAIL = os.getenv(
    "GTM_GROUP_EMAIL",
    "gtm@savannahinformatics.com",
)
CLIENT_SUCCESS_GROUP_EMAIL = os.getenv(
    "CLIENT_SUCCESS_GROUP_EMAIL",
    "clientsuccess@savannahinformatics.com",
)


""" Charge Master """
CHARGE_MASTER = {
    "host": os.environ.get("CHARGE_MASTER_HOST"),
    "token_url": os.environ.get("CHARGE_MASTER_TOKEN_URL"),
    "client_id": os.environ.get("CHARGE_MASTER_CLIENT_ID"),
    "client_secret": os.environ.get("CHARGE_MASTER_CLIENT_SECRET"),
    "scheme": os.environ.get("CHARGE_MASTER_SCHEME", "http"),
    "username": os.environ.get("CHARGE_MASTER_USERNAME"),
    "password": os.environ.get("CHARGE_MASTER_PASSWORD"),
    "grant_type": os.environ.get("CHARGE_MASTER_GRANT_TYPE"),
    "SCOPES": AUTH_SERVER_API_SCOPES,
}

""" Is_client """
IS_CLIENT = {
    "host": os.environ.get("IS_HOST"),
    "token_url": os.environ.get("IS_TOKEN_URL"),
    "client_id": os.environ.get("IS_CLIENT_ID"),
    "client_secret": os.environ.get("IS_CLIENT_SECRET"),
    "scheme": os.environ.get("IS_SCHEME", "http"),
    "username": os.environ.get("IS_USERNAME"),
    "password": os.environ.get("IS_PASSWORD"),
}

""" SMS """
SIL_COMMS_TRANSACTIONAL_SENDER_ID = os.getenv(
    "SIL_COMMS_TRANSACTIONAL_SENDER_ID", "BeWellApp"
)
SIL_COMMS_PROMOTIONAL_SENDER_ID = os.getenv(
    "SIL_COMMS_PROMOTIONAL_SENDER_ID", "BeWellInfo"
)
SIL_COMMS_BUSINESS_PARTNER_APP_ID = os.getenv("SIL_COMMS_BUSINESS_PARTNER_APP_ID", "")
SIL_COMMS_API_CONFIG = {
    "api_host": os.getenv("SIL_COMMS_API_HOST"),
    "api_scheme": os.getenv("SIL_COMMS_API_SCHEME"),
    "oauth_client_id": os.getenv("SIL_COMMS_OAUTH_CLIENT_ID"),
    "oauth_client_secret": os.getenv("SIL_COMMS_OAUTH_CLIENT_SECRET"),
    "user_email": os.getenv("SIL_COMMS_USER_EMAIL"),
    "user_password": os.getenv("SIL_COMMS_USER_PASSWORD"),
    "token_url": os.getenv("SIL_COMMS_AUTH_TOKEN_URL"),
}
SMS_OLD_AFTER = int(os.getenv("SMS_OLD_AFTER", 2))
default_white_listed_contacts = (
    "+254721570768,+254700090954,+254723002959,+254721816365,"
    "+254707777923,+254714575274,+254725332343,+254743304704,"
    "+254724447010,+254720566873,+254720601060,+254701436954,"
    "+254796054406,+254710744748,+254721787472,+254710378871,"
    "+254723762995,+254721939433,+254757169385,+254714575274,"
    "+254714916889,+254799757242,+254746104917,+254703730183,"
    "+254717356476,+254780621229,+254735899967,+254715658227,"
    "+254707705021"
)
WHITELISTED_TEST_RECIPIENTS = split_env_values(
    os.getenv("WHITELISTED_TEST_RECIPIENTS", default_white_listed_contacts)
)
SEGMENT_DELAY_BEFORE_SENDING_INSTANT_MESSAGE = int(
    os.getenv("SEGMENT_DELAY_BEFORE_SENDING_INSTANT_MESSAGE", 30)
)
SIL_TERMS_AND_CONDITIONS_LINK = os.getenv(
    "SIL_TERMS_AND_CONDITIONS_LINK",
    "https://www.savannahinformatics.com/privacy-policy",
)

default_sms_appointment_creation_en_template = (
    "Dear {fname}, an appointment for {specialty} "
    "on {date} {time_slot} has been created at {provider_name}"
)
default_sms_appointment_reminder_en_template = (
    "Dear {fname}, we would wish to remind you of your scheduled "
    "appointment at {provider_name} on {date} {time_slot}. "
    "If you need to reschedule, please call us on {org_phone_number}"
)
default_sms_appointment_reschedule_en_template = (
    "Dear {fname}, we would like to inform you that your appointment "
    "for {specialty} at {provider_name} has been rescheduled to "
    "{date} {time_slot}. "
    "In case of any concerns please call us on {org_phone_number}."
)
default_sms_appointment_cancellation_en_template = (
    "Dear {fname}, due to unavoidable circumstances, "
    "we regret to inform you that your {specialty} appointment "
    "at {provider_name} on {date} {time_slot} has been cancelled"
)
default_sms_check_in_creation_en_template = (
    "Hello, an appointment has been scheduled at {provider_name} "
    "on {date}. "
    "In case of any concerns please call us on {org_phone_number}."
)
default_sms_post_visit_survey_en_template = (
    "Hi {fname}, following your visit at {provider_name} on {date}, "
    "kindly assist us understand how we can serve you better by "
    "following {link} to fill in our survey"
)
default_sms_visit_summary_en_template = (
    "Dear {fname}, Thank you for choosing our services at {provider_name} on {date}. "
    "You can access your receipt here {link} "
    "In case of any concerns please call us on {org_phone_number}."
)
default_sms_patient_registration_en_template = (
    "Hi {fname}, you've been registered at {provider_name}. "
    "Your patient ID is {patient_id}. "
    "Please read our terms and conditions here "
    "https://www.savannahinformatics.com/privacy-policy "
)
default_sms_patient_registration_sw_template = (
    "Habari {fname}, umesajiliwa kwa {provider_name}. "
    "Kitambulisho chako cha huduma ni {patient_id}. "
    "Tafadhali soma sheria na masharti yetu hapa "
    "https://www.savannahinformatics.com/privacy-policy "
)
default_sms_practitioner_daily_digest_en_template = (
    "Hi {title} {fname}, you have {appointments} appointment(s) "
    "today at {provider_name}. To view more, click {url}"
)
default_sms_patient_global_health_id_en_template = (
    "Welcome to {provider_name}! Your registration is complete. "
    "Your Health ID is {health_id}. "
    "Stay healthy with regular screenings. Thank you!"
)
default_sms_patient_communication_consent_otp_en_template = (
    "Hi {fname}, your OTP for {provider_name} communication consent is {code}."
)
DEFAULT_SMS_INTENTION_TEMPLATES = {
    "APPOINTMENT_CREATION": default_sms_appointment_creation_en_template,
    "APPOINTMENT_REMINDER": default_sms_appointment_reminder_en_template,
    "APPOINTMENT_RESCHEDULE": default_sms_appointment_reschedule_en_template,
    "APPOINTMENT_CANCELLATION": default_sms_appointment_cancellation_en_template,
    "CHECK_IN_CREATION": default_sms_check_in_creation_en_template,
    "POST_VISIT_SURVEY": default_sms_post_visit_survey_en_template,
    "VISIT_SUMMARY": default_sms_visit_summary_en_template,
    "PATIENT_REGISTRATION_EN": default_sms_patient_registration_en_template,
    "PATIENT_REGISTRATION_SW": default_sms_patient_registration_sw_template,
    "PRACTITIONER_DAILY_DIGEST": default_sms_practitioner_daily_digest_en_template,
    "PATIENT_GLOBAL_HEALTH_ID": default_sms_patient_global_health_id_en_template,
    "PATIENT_COMMUNICATION_CONSENT_OTP": default_sms_patient_communication_consent_otp_en_template,  # noqa: B950
}

""" ERP """
ERP_API_CONFIG = {
    "api_host": os.getenv("ERP_API_HOST"),
    "api_scheme": os.getenv("ERP_API_SCHEME", "https"),
    "oauth_client_id": os.getenv("ERP_OAUTH_CLIENT_ID"),
    "oauth_client_secret": os.getenv("ERP_OAUTH_CLIENT_SECRET"),
    "user_email": os.getenv("ERP_USER_EMAIL"),
    "user_password": os.getenv("ERP_USER_PASSWORD"),
    "token_url": os.getenv("ERP_AUTH_TOKEN_URL"),
}
SYNC_WITH_ERP = get_bool_env("SYNC_WITH_ERP", "False")
DISABLE_ORG_SETUP = False
TRANSACTING_SIL_ORG_SLADE_CODE = int(
    os.getenv("TRANSACTING_SIL_ORG_SLADE_CODE", 1),
)

""" Celery """
# Redis rather than RabbitMQ: it is already in the stack for the cache, and
# Celery supports it as a broker. Kombu has no NATS transport, so the events
# clinical publishes over NATS and Django's background jobs stay separate.
BROKER_URL = os.getenv("BROKER_URL", "redis://localhost:6379/1")
RESULT_BACKEND = os.getenv("RESULT_BACKEND", BROKER_URL)
CELERY_TIMEZONE = TIME_ZONE
CELERY_DEFAULT_QUEUE = "advantage_tasks"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_RESULT_EXPIRES = 300  # 5 minutes
CELERY_TASK_HIGH_PRIORITY = 10
CELERY_TASK_MEDIUM_PRIORITY = 5
CELERY_TASK_LOW_PRIORITY = 1
CELERY_TASK_QUEUES = (
    Queue(
        CELERY_DEFAULT_QUEUE,
        Exchange(CELERY_DEFAULT_QUEUE),
        routing_key=CELERY_DEFAULT_QUEUE,
        queue_arguments={"x-max-priority": CELERY_TASK_HIGH_PRIORITY},
    ),
)
CELERYBEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

""" STATSD """
STATSD_HOST = os.getenv("STATSD_HOST", "127.0.0.1")
STATSD_PORT = int(os.getenv("STATSD_PORT", 8125))

""" Quintus """
QUINTUS_BACKEND_URL = os.getenv("QUINTUS_BACKEND_URL")

""" Health CRM """
HEALTH_CRM_API_URL = os.getenv("HEALTH_CRM_API_URL")
HEALTH_CRM_SERVICE_CODE = os.getenv("HEALTH_CRM_SERVICE_CODE")
SYNC_WITH_HEALTH_CRM = get_bool_env("SYNC_WITH_HEALTH_CRM", "False")

""" Clinical Server """
CLINICAL_SERVICE_URL = os.getenv("CLINICAL_SERVICE_URL")
SYNC_WITH_CLINICAL_SERVICE = get_bool_env(
    "SYNC_WITH_CLINICAL_SERVICE",
    "False",
)

""" Matrix """
MATRIX_HOME_SERVER = os.getenv("MATRIX_HOME_SERVER")
MATRIX_BOT_UID = os.getenv("MATRIX_BOT_UID")
MATRIX_BOT_PASSWORD = os.getenv("MATRIX_BOT_PASSWORD")
MATRIX_SECRET = os.getenv("MATRIX_SECRET")

""" External Integrations """
INTEGRATION_CONFIG_ENCRYPTION_KEY = os.getenv(
    "INTEGRATION_CONFIG_ENCRYPTION_KEY",
    "1t1qtJ1S1N00V3kSc_zyF-eqJH-eQPL3YqIO1oSwXEU=",
).encode("utf-8")


"""SIL backup utils """
SIL_BACKUP_UTILS = {
    "ENABLED": os.getenv("BACKUP_ON", True),
    "SYSTEM": "advantage",
    "VERSION": __version__,
    "SITE": ENVIRONMENT,
    "ENVIRONMENT": ENVIRONMENT,
    "S3": {
        "AWS_ACCESS_KEY_ID": os.getenv("BACKUP_ACCESS_KEY_ID"),
        "AWS_SECRET_ACCESS_KEY": os.getenv("BACKUP_SECRET_KEY"),
        "AWS_REGION": os.getenv("BACKUP_REGION"),
        "BUCKET": os.getenv("BACKUP_BUCKET_NAME"),
    },
    "ENABLED_DATABASES": [
        "default",
    ],
    "FROM_EMAIL": OUTGOING_EMAIL_SOURCE,
    "REPORTING_EMAILS": os.getenv(
        "BACKUP_MONITORING_EMAIL", "edi.monitoring@slade360.co.ke"
    ).split(","),
    "PG_DUMP_PATH": os.getenv("BACKUP_PG_DUMP_PATH"),
    "ENCRYPTION_PUBLIC_KEY_PATH": os.getenv("BACKUP_ENCRYPTION_PUBLIC_KEY_PATH"),
}

"""Shlink configuration"""
SIL_SHLINK = {
    "SHLINK_SERVER_URL": os.getenv("SHLINK_SERVER_URL"),
    "SHLINK_API_KEY": os.getenv("SHLINK_API_KEY"),
    "SHLINK_CUSTOM_DOMAIN": os.getenv("SHLINK_CUSTOM_DOMAIN"),
}

"""Provider IS"""
SYNC_WITH_PROVIDER_IS = get_bool_env("SYNC_WITH_PROVIDER_IS", "False")

"""Tariffs"""
TARRIFS_AUTH_SERVER_LOGIN_CONFIG = {
    "HOST": os.getenv("TARIFF_AUTH_SERVER_HOST"),
    "KEY": os.getenv("TARIFF_AUTH_SERVER_CLIENT_ID"),
    "SECRET": os.getenv("TARIFF_AUTH_SERVER_SECRET_KEY"),
    "USER_EMAIL": os.getenv("TARIFF_AUTH_SERVER_USER_EMAIL"),
    "USER_PASSWORD": os.getenv("TARIFF_AUTH_SERVER_USER_PASSWORD"),
    "TOKEN_URL": os.getenv("TARIFF_AUTH_SERVER_TOKEN_URL"),
}
TARIFF_BASE_URL = os.getenv("TARIFF_BASE_URL")
