"""Integrations tasks."""
import logging
import uuid
from typing import Any, Literal

from celery.schedules import crontab
from django.apps import apps
from django.conf import settings
from django.db.models import Q
from sil_monitoring import Monitor
from sil_monitoring.backends import StatsD

from sil_advantage.common.tasks import BaseTaskWithRetry
from sil_advantage.config import celery_app

LOGGER = logging.getLogger(__file__)


@celery_app.on_after_finalize.connect
def setup_periodic_tasks(**kwargs: Any) -> None:
    """Register the periodic tasks with Celery.

    Args:
        **kwargs: Arbitrary keyword arguments.
    """
    # import's here due to circular dependency issues
    from sil_advantage.integrations.files.google_drive import (
        open_google_drive_channels,
    )

    celery_app.add_periodic_task(
        crontab(hour=3, minute=0),
        open_google_drive_channels,
        name="open-google-drive-channels",
        priority=settings.CELERY_TASK_MEDIUM_PRIORITY,
    )

    celery_app.add_periodic_task(
        crontab(hour="0-7/2,8-18,19-23/2", minute=15),
        report_sync_linking_stats,
        name="report-sync-linking-stats",
        priority=settings.CELERY_TASK_LOW_PRIORITY,
    )


@celery_app.task(base=BaseTaskWithRetry)
def sync_updates_to_remote(
    model_name: str,
    pk: uuid.UUID,
    system: Literal["ERP", "HEALTH_CRM", "CLINICAL_SERVICE"],
    operation: Literal[
        "CREATE",
        "UPDATE",
        "DELETE",
    ],
) -> None:
    """Sync updates to the remote system."""
    Model = apps.get_model(model_name)

    try:
        instance = Model.objects.get(pk=pk)
        match system:
            case "ERP":
                instance._perform_operation_on_erp(operation)
            case "HEALTH_CRM":
                instance._perform_operation_on_health_crm(operation)
            case "CLINICAL_SERVICE":
                instance._perform_operation_on_clinical_service(operation)
            case _:
                LOGGER.error(f"Unsupported system {system}.")
    except Model.DoesNotExist:
        LOGGER.error(f"Object with ID {pk} of type {model_name} does not exist.")


@celery_app.task(base=BaseTaskWithRetry)
def report_sync_linking_stats() -> None:
    """Report sync linking statistics to Grafana."""
    monitor = Monitor(
        StatsD(
            settings.STATSD_HOST,  # type: ignore  # import cycle issue
            settings.STATSD_PORT,  # type: ignore  # import cycle issue
            backend="telegraf",
        )
    )

    models = {
        "billing.clinicalorder": {
            "ERP": Q(sales_order_id__isnull=True),
        },
        "billing.invoice": {
            "ERP": Q(sales_invoice_id__isnull=True),
        },
        "billing.billableitem": {
            "ERP": Q(
                sales_order_line_id__isnull=True,
                sales_invoice_line_id__isnull=True,
            )
        },
        "billing.refund": {
            "ERP": Q(sales_credit_note_id__isnull=True),
        },
        "billing.refundline": {
            "ERP": Q(sales_credit_note_line_id__isnull=True),
        },
        "common.organisation": {
            "CLINICAL_SERVICE": Q(tenant_id__isnull=True),
        },
        "sil_auth.siluser": {
            "MATRIX": Q(matrix_user_id__isnull=True),
        },
        "notifications.group": {
            "MATRIX": Q(matrix_room_id__isnull=True),
        },
        "patients.patient": {
            "ERP": Q(customer_id__isnull=True),
            "CLINICAL_SERVICE": Q(clinical_id__isnull=True),
            "HEALTH_CRM": Q(global_health_id__isnull=True),
        },
        "visits.visit": {
            "CLINICAL_SERVICE": Q(
                episode_of_care_id__isnull=True,
                created__date__gte="2023-08-09",
            ),
        },
        "visits.servicerequest": {
            "CLINICAL_SERVICE": Q(
                encounter_id__isnull=True,
                created__date__gte="2023-08-09",
            ),
        },
    }
    for model_name, remotes in models.items():
        Model = apps.get_model(model_name)

        for remote, query in remotes.items():
            count = Model.objects.filter(query).count()
            monitor.gauge(
                "unlinked_objects",
                count,
                tags={"model": model_name, "remote": remote},
            )
