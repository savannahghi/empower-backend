"""Scheduling tasks."""
from typing import Any

import pytz
from celery.schedules import crontab
from django.conf import settings
from django.utils import timezone

from sil_advantage.common.tasks import BaseTaskWithRetry
from sil_advantage.config import celery_app
from sil_advantage.scheduling.models import Appointment


@celery_app.on_after_finalize.connect
def setup_periodic_tasks(**kwargs: Any) -> None:
    """Register the periodic tasks with Celery.

    Args:
        **kwargs: Arbitrary keyword arguments.
    """
    celery_app.add_periodic_task(
        # execute every hour
        crontab(minute=0, hour="*"),
        send_appointment_reminders,
        name="send-appointment-reminders",
        priority=settings.CELERY_TASK_HIGH_PRIORITY,
    )

    celery_app.add_periodic_task(
        # execute every day at 10 PM
        crontab(minute=0, hour=22),
        update_appointment_status_to_no_show,
        name="update-appointment-status-to-no-show",
        priority=settings.CELERY_TASK_HIGH_PRIORITY,
    )


@celery_app.task(base=BaseTaskWithRetry)
def send_appointment_reminders() -> None:
    """Send appointment reminders."""
    local_tz = pytz.timezone(settings.TIME_ZONE)
    now = timezone.now().astimezone(local_tz)
    appointments = Appointment.objects.filter(
        pending_reminders__0__date=now.date(),
        pending_reminders__0__hour=now.hour,
        appointment_status="BOOKED",
    )
    for appt in appointments:
        appt.send_appointment_reminder_message()
        appt.pending_reminders.pop(0)
        appt.save(update_fields=["pending_reminders"])


@celery_app.task(base=BaseTaskWithRetry)
def update_appointment_status_to_no_show() -> None:
    """Update appointment statuses to NO_SHOW."""
    local_tz = pytz.timezone(settings.TIME_ZONE)
    now = timezone.now().astimezone(local_tz)
    appointments_to_update_status = Appointment.objects.filter(
        end__lt=now, appointment_status="BOOKED"
    )
    for appt in appointments_to_update_status:
        appt.appointment_status = "NO_SHOW"
        appt.save(update_fields=["appointment_status"])
