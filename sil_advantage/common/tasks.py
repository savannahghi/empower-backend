"""Common tasks."""
import logging
import time
from functools import cached_property
from typing import Any, Dict
from urllib.parse import urlencode

from aiohttp.client_exceptions import ClientError
from billiard.einfo import ExceptionInfo
from celery.schedules import crontab
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.db import OperationalError
from django.utils import timezone
from requests import ConnectionError, Timeout, TooManyRedirects
from sil_backup_utils.tasks import backup_dbs
from sil_monitoring import Monitor
from sil_monitoring.backends import StatsD
from sil_shlink import ShlinkPayload
from urllib3.exceptions import MaxRetryError

from sil_advantage.common.models import Organisation
from sil_advantage.common.utilities.urlshortener import shlink_shorten_url
from sil_advantage.config import celery_app
from sil_advantage.notifications.sms.utils import send_custom_sms
from sil_advantage.practitioners.models import Practitioner

LOGGER = logging.getLogger(__file__)


class BaseTaskWithRetry(celery_app.Task):  # type: ignore
    """Base Celery Task that enables task retries.

    It follows an exponential backoff strategy to exponentially increase
    the amount of time between subsequent retries.
    It also introduces jitter (random offsets to the countdown
    till the next retry) to mitigate the Thundering herd problem.
        The thundering herd problem occurs when a large number of processes or
        threads waiting for an event are awoken when that event occurs,
        but only one process is able to handle the event (Wikipedia).

    As of RabbitMQ version 3.8.17, the max `retry_back_off` is 30 minutes.
    Setting values above that might lead to Celery workers terminating with a
    `PreconditionFailed` error. This can be addressed by increasing
    the `consumer_timeout` in `rabbitmq.conf`.
    """

    # Retries
    autoretry_for = (
        ConnectionError,
        TooManyRedirects,
        Timeout,
        MaxRetryError,
        ClientError,
        OperationalError,
    )
    max_retries = 4
    # This will retry a task after 64s, 128s, 256s, & 512s
    #  (total = 16 minutes) before giving up
    retry_backoff = 64
    retry_backoff_max = 1024
    retry_jitter = True

    # Results
    ignore_result = True

    # Events
    send_events = False

    @cached_property
    def reporting_name(self) -> str:
        """Name to use when reporting metrics."""
        return self.name.split(".")[-1]

    @cached_property
    def monitor(self) -> Monitor:
        """Return an instance of `Monitor`."""
        return Monitor(
            backend=StatsD(
                settings.STATSD_HOST,  # type: ignore  # import cycle issue
                settings.STATSD_PORT,  # type: ignore  # import cycle issue
                backend="telegraf",
            ),
        )

    def _log_task_duration(self, task_id: str) -> None:
        """Log task duration."""
        timer = self.monitor.timer(
            "celery_tasks_duration",
            tags={"name": self.reporting_name},
        )
        timer._start = cache.get(
            task_id,
            default=time.time(),
        )
        timer.stop()

    def before_start(
        self,
        task_id: str,
        args: tuple,
        kwargs: dict,
    ) -> None:
        """Run by the worker before the task starts executing."""
        cache.set(
            task_id,
            time.time(),
            timeout=60 * 60,
        )

    def on_success(
        self,
        retval: Any,
        task_id: str,
        args: tuple,
        kwargs: dict,
    ) -> None:
        """Run by the worker if the task executes successfully."""
        self.monitor.increment(
            "celery_tasks_succeeded",
            tags={"name": self.reporting_name},
        )
        self._log_task_duration(task_id)
        cache.delete(task_id)

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: ExceptionInfo,
    ) -> None:
        """Run by the worker when the task is to be retried."""
        self.monitor.increment(
            "celery_tasks_retried",
            tags={
                "name": self.reporting_name,
                "exception": exc.__class__.__name__,
            },
        )
        self._log_task_duration(task_id)
        cache.delete(task_id)

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: ExceptionInfo,
    ) -> None:
        """Run by the worker when the task fails."""
        self.monitor.increment(
            "celery_tasks_failed",
            tags={
                "name": self.reporting_name,
                "exception": exc.__class__.__name__,
            },
        )
        self._log_task_duration(task_id)
        cache.delete(task_id)


@celery_app.on_after_finalize.connect
def setup_periodic_tasks(**kwargs: Any) -> None:
    """Register the periodic tasks with Celery.

    Args:
        **kwargs: Arbitrary keyword arguments.
    """
    celery_app.add_periodic_task(
        crontab(hour=2, minute=45),
        sync_org_updates_with_remote,
        name="sync-org-updates-with-remote",
        priority=settings.CELERY_TASK_LOW_PRIORITY,
    )
    celery_app.add_periodic_task(
        crontab(hour=0, minute=0),
        backup_dbs,
        name="backup-dbs",
        priority=settings.CELERY_TASK_LOW_PRIORITY,
    )
    celery_app.add_periodic_task(
        crontab(hour=7, minute=0),
        send_practitioner_daily_digest_message,
        name="send-practitioner-daily-digest-message",
        priority=settings.CELERY_TASK_LOW_PRIORITY,
    )
    celery_app.add_periodic_task(
        crontab(minute="*/1"),
        retry_failed_to_sync_objects,
        name="retry-failed-to-sync-objects",
        priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
    )


@celery_app.task(base=BaseTaskWithRetry)
def sync_org_updates_with_remote() -> None:
    """Sync organisation updates with remote.

    This:
        1. Pulls branches from ERP and creates them as facilities
            on the clinical server
        2. Pulls workstations from ERP and updates the queues
            on Advantage
    """
    orgs = Organisation.objects.filter(active=True)
    for org in orgs.iterator():
        org.create_tenant_on_clinical_server()
        org.create_customer_on_erp()
        org.create_facilities_on_clinical_server()
        org.create_queues_for_workstations()


@celery_app.task(base=BaseTaskWithRetry)
def send_practitioner_daily_digest_message() -> None:
    """Sends practitioner daily digest message."""
    # import's here due to cyclic dependency issues
    from sil_advantage.scheduling.models import Appointment, Schedule

    practitioners = Practitioner.objects.select_related("person", "organisation")

    for practitioner in practitioners:
        phone_number = practitioner.person.phone_number

        if phone_number:
            now = timezone.now()
            today_start = now.replace(hour=0, minute=0, second=0)
            today_end = now.replace(hour=23, minute=59, second=59)

            appointments = Appointment.objects.filter(
                slot__schedule__practitioner__id=practitioner.id,
                start__gte=today_start,
                end__lte=today_end,
            ).count()

            if not appointments:
                error_msg = "No appointments scheduled for this practitioner"
                LOGGER.warning(error_msg)
                continue

            schedule = Schedule.objects.filter(practitioner=practitioner).latest(
                "created"
            )

            org = practitioner.organisation
            branch_id = practitioner.branch_id
            priority = settings.CELERY_TASK_LOW_PRIORITY
            data = {
                "ordering": "start",
                "page_size": 5,
                "page": 1,
                "start": today_start.date(),
                "schedule_id": schedule.id,
            }
            long_url = settings.ADVANTAGE_FRONTEND_URL + "{url}{querystring}".format(
                url="/advantage/practitioner_appointments",
                querystring="?" + urlencode(data, doseq=True),
            )
            payload = ShlinkPayload(
                long_url=long_url, domain=settings.SIL_SHLINK["SHLINK_CUSTOM_DOMAIN"]
            )
            short_url = shlink_shorten_url(payload=payload)

            send_custom_sms(
                "PRACTITIONER_DAILY_DIGEST",
                phone_number,
                org,
                branch_id,
                practitioner.person,
                priority,
                title=practitioner.person.title,
                appointments=appointments,
                url=short_url,
            )
        else:
            error_msg = "No phone number configured for this practitioner"
            LOGGER.warning(error_msg)


@celery_app.task()
def retry_failed_to_sync_objects() -> None:
    """Retries for objects that have failed to sync to remote services(erp)."""
    # List of model sync configurations
    if not settings.SYNC_WITH_ERP:
        return
    sync_configurations = [
        {
            "app_label": "patients",
            "model_name": "Patient",
            "filters": {"customer_id__isnull": True},
        },
        {
            "app_label": "billing",
            "model_name": "Invoice",
            "filters": {"sales_invoice_id__isnull": True},
        },
        {
            "app_label": "billing",
            "model_name": "BillableItem",
            "filters": {"sales_invoice_line_id__isnull": True},
        },
        {
            "app_label": "billing",
            "model_name": "Refund",
            "filters": {"sales_credit_note_id__isnull": True},
        },
        {
            "app_label": "billing",
            "model_name": "RefundLine",
            "filters": {"sales_credit_note_line_id__isnull": True},
        },
    ]

    for config in sync_configurations:
        sync_model_objects_to_erp(config)


def sync_model_objects_to_erp(config: Dict[str, Any]) -> None:
    """This is a generic helper function that syncs updates to ERP.

    The function:
    - Dynamically retrieves the model class using apps.get_model.
    - Filters objects that need to be synced based on the provided
      filters.
    - Attempts to sync each object, logging any exceptions that occur.
    """
    from sil_advantage.integrations.tasks import sync_updates_to_remote

    app_label = config["app_label"]
    model_name = config["model_name"]
    filters = config["filters"]

    # get the model class
    model_class = apps.get_model(app_label, model_name)

    # Fetch objects that need to be synced
    objects_to_sync = model_class.objects.filter(**filters)

    for obj in objects_to_sync:
        try:
            sync_updates_to_remote(
                f"{app_label}.{model_name.lower()}", obj.id, "ERP", "CREATE"
            )
        except Exception:
            failed_to_sync = {
                f"{model_name} ID": str(obj.id),
                "Organisation": getattr(obj, "organisation", "N/A"),
            }
            msg = f"Unable to sync {model_name} objects to ERP"
            LOGGER.error(msg, extra=failed_to_sync, exc_info=True)
