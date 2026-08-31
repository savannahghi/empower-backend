"""Link Celery to Django settings."""
import os

from celery import Celery

from sil_advantage.config.settings import CELERY_TASK_LOW_PRIORITY

# set the default Django settings module for the Celery program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sil_advantage.config.settings")
app = Celery("sil-advantage")

# Using a string here means the worker will not have to
# pickle the object when using Windows.
app.config_from_object("django.conf:settings")
app.conf.task_default_priority = CELERY_TASK_LOW_PRIORITY
app.autodiscover_tasks()
