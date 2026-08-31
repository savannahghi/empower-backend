"""Test scheduling tasks."""
from datetime import timedelta
from unittest.mock import patch

import pytest
import pytz
from django.conf import settings
from django.utils.dateparse import parse_datetime
from model_bakery import baker

from sil_advantage.common.models import Person, PersonContact
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.patients.models import Patient
from sil_advantage.practitioners.models import Practitioner
from sil_advantage.scheduling import SLOT_STATUS
from sil_advantage.scheduling.models import Appointment, Schedule, Slot
from sil_advantage.scheduling.tasks import (
    celery_app,
    send_appointment_reminders,
    setup_periodic_tasks,
    update_appointment_status_to_no_show,
)
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.scheduling.tasks."


@pytest.mark.usefixtures("default_transactional_sender")
class SchedulingTasksTestCase(LoggedInMixin):
    """Test Scheduling Tasks."""

    def setUp(self) -> None:
        """Setup test environment."""
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")
        super().setUp()

    def test_registering_scheduling_tasks(self):
        """Test registering tasks with Celery."""
        setup_periodic_tasks()
        assert (
            "sil_advantage.scheduling.tasks.send_appointment_reminders"
            in celery_app.tasks
        )
        assert (
            "sil_advantage.scheduling.tasks.update_appointment_status_to_no_show"
            in celery_app.tasks
        )

    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    @patch(MOCK_ROOT + "timezone.now")
    def test_send_appointment_reminders(self, mock_timezone, mock_send_sms):
        """Test sending appointment reminders."""
        mock_timezone.return_value = parse_datetime("2042-02-27T10:00:00.647504Z")

        patient = baker.make(
            Patient, person__first_name="Jane", person__last_name="Doe"
        )
        baker.make(
            PersonContact,
            person=patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )

        person = baker.make(Person)
        practitioner = baker.make(Practitioner, person=person)

        schedule = baker.make(
            Schedule,
            specialty="OTHER",
            practitioner=practitioner,
            slot_duration=30,
            organisation=self.global_organisation,
        )
        day = parse_datetime("2042-02-28 00:05+00:00") + timedelta(hours=10)
        slot_start = day + timedelta(minutes=30)
        slot_end = slot_start + timedelta(minutes=30)
        slot = baker.make(
            Slot,
            start=slot_start,
            end=slot_end,
            schedule=schedule,
            status=SLOT_STATUS.FREE,
            organisation=self.global_organisation,
        )
        kwargs = {
            "reason": "some reason",
            "description": "needs spectacles",
            "start": slot_start,
            "end": slot_end,
            "slot": slot,
            "organisation": self.user.organisation,
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
            "appointment_status": "BOOKED",
            "patient": patient,
            "branch_id": "abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        }
        appt = baker.make(Appointment, **kwargs)
        assert len(appt.pending_reminders) == 1
        # ignore appointment creation mock call
        mock_send_sms.reset_mock()

        send_appointment_reminders()

        appt.refresh_from_db()
        assert len(appt.pending_reminders) == 0

        # test idempotency
        send_appointment_reminders()

        date_str = slot_start.strftime("%a %b-%d")
        local_tz = pytz.timezone(settings.TIME_ZONE)
        time_slot = slot_start.astimezone(local_tz).strftime("%-I:%M%p")
        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=5,
            args=(
                "APPOINTMENT_REMINDER",
                "Dear Jane, we would wish to remind you of your "
                "scheduled appointment at Demo Hospital on "
                f"{date_str} {time_slot}. If you need to reschedule, "
                "please call us on +254799999999",
                ["+254712345678"],
                self.global_organisation.slade_code,
                appt.branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )

    @patch(MOCK_ROOT + "timezone.now")
    def test_update_appointment_status_to_no_show(self, mock_timezone):
        """Test updating appointments to NO_SHOW status."""
        mock_timezone.return_value = parse_datetime("2042-02-27T10:00:00.647504Z")

        patient = baker.make(
            Patient, person__first_name="Jane", person__last_name="Doe"
        )

        schedule = baker.make(
            Schedule,
            specialty="OTHER",
            practitioner=baker.make(Practitioner, person=baker.make(Person)),
            slot_duration=30,
            organisation=self.global_organisation,
        )

        # Create an appointment with future dates to avoid validation errors
        future_time = mock_timezone.return_value + timedelta(minutes=60)
        slot = baker.make(
            Slot,
            start=future_time,
            end=future_time + timedelta(minutes=30),
            schedule=schedule,
            status=SLOT_STATUS.FREE,
            organisation=self.global_organisation,
        )
        no_show_appt = baker.make(
            Appointment,
            start=future_time,
            end=future_time + timedelta(minutes=30),
            appointment_status="BOOKED",
            patient=patient,
            slot=slot,
            organisation=self.global_organisation,
        )

        # Update the slot and appointment to past dates
        past_time = mock_timezone.return_value - timedelta(minutes=30)
        slot.start = past_time - timedelta(minutes=30)
        slot.end = past_time
        slot.save()
        no_show_appt.start = past_time - timedelta(minutes=30)
        no_show_appt.end = past_time
        no_show_appt.save()

        update_appointment_status_to_no_show()

        no_show_appt.refresh_from_db()
        assert no_show_appt.appointment_status == "NO_SHOW"
