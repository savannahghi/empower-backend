"""Test scheduling models."""
import re
from datetime import timedelta
from unittest.mock import patch

import pytest
import pytz
from django.conf import settings
from django.core.exceptions import ValidationError as DjValidationError
from django.test import override_settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from model_bakery import baker
from rest_framework.serializers import ValidationError

from sil_advantage.common.models.common_models import Person, PersonContact
from sil_advantage.notifications.sms.models import SenderID
from sil_advantage.patients.models import Patient
from sil_advantage.practitioners.models import Practitioner
from sil_advantage.scheduling import APPOINTMENT_STATUS, SLOT_STATUS
from sil_advantage.scheduling.models import (
    Appointment,
    Schedule,
    ScheduleTiming,
    Slot,
)
from tests.common.test_common_views import LoggedInMixin

MOCK_ROOT = "sil_advantage.scheduling.models."


class ScheduleTimingTest(LoggedInMixin):
    """Test the availability."""

    def test_validate_start_less_than_end(self):
        """Validate start is less than end."""
        expected_error = re.escape(
            "{'end': ['The timing end must be greater than its start.']}"
        )
        with pytest.raises(DjValidationError, match=expected_error):
            baker.make(
                ScheduleTiming,
                start="12:00",
                end="08:00",
                schedule__slot_duration=15,
            )


class SlotTest(LoggedInMixin):
    """Test the slots."""

    def setUp(self):
        """Test that slots contains fields for __slots__."""
        super().setUp()
        self.start_date = timezone.now() + timezone.timedelta(500)
        self.end_date = self.start_date + timezone.timedelta(500)

        self.start_date_less = parse_datetime("2015-10-01T10:20:30.647504Z")
        self.end_date_less = parse_datetime("2015-09-01T10:20:30.647504Z")
        person = baker.make(Person)
        practitioner = baker.make(Practitioner, person=person)

        self.sch = baker.make(
            Schedule,
            practitioner=practitioner,
            organisation=self.user.organisation,
            slot_duration=30,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )

    def test_slot_unicode(self):
        """Test to ensure that slots are represented by its start and end."""
        start = timezone.now() + timezone.timedelta(500)
        end = start + timezone.timedelta(500)

        slot = baker.make(
            Slot,
            start=start,
            end=end,
            organisation=self.user.organisation,
            schedule=self.sch,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        assert str(self.sch) == "-".join(
            [
                self.sch.practitioner.person.get_full_name(),
                self.sch.practitioner.qualification,
            ]
        )
        start_string = start.strftime("%Y-%m-%d %H:%MHrs")
        end_string = end.strftime("%Y-%m-%d %H:%MHrs")
        slot_title = " - ".join([start_string, end_string])
        assert str(slot) == slot_title

    def test_slot_date_greater(self):
        """Ensure that the appointment date is greater than current."""
        slot = Slot(
            schedule=self.sch,
            organisation=self.user.organisation,
            status=SLOT_STATUS.BUSY,
            start=self.start_date,
            end=self.end_date,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        slot.save()

    def test_slot_date_lesser(self):
        """Test ValidationError if the date is less than current time."""
        status = SLOT_STATUS.BUSY
        date_string = "Start date must be greater than current time"
        with pytest.raises(ValidationError) as g:
            slot = Slot(
                schedule=self.sch,
                organisation=self.user.organisation,
                status=status,
                start=self.start_date_less,
                end=self.end_date_less,
                created_by=self.user.pk,
                updated_by=self.user.pk,
            )
            slot.save()
            assert date_string in g.exception.messages

    def test_slot_end_less_than_start(self):
        """Test if end date is less than start."""
        start_slot = timezone.now() + timezone.timedelta(470)
        end_slot = start_slot - timezone.timedelta(20)
        status = SLOT_STATUS.BUSY

        with pytest.raises(ValidationError) as g:
            slot = Slot(
                schedule=self.sch,
                organisation=self.user.organisation,
                status=status,
                start=start_slot,
                end=end_slot,
                created_by=self.user.pk,
                updated_by=self.user.pk,
            )
            slot.save()
            error_msg = {"end": "End date must be greater than start date"}
            assert error_msg in g.exception.messages

    def test_slot_start_historical_dates(self):
        """Test to ensure that slots are saved with valid dates."""
        start_slot = timezone.now() - timezone.timedelta(50)
        end_slot = timezone.now() + timezone.timedelta(50)
        status = SLOT_STATUS.BUSY
        start_date_str = "Slot start date must be greater than currentdate"

        with pytest.raises(ValidationError) as g:
            slot = Slot(
                schedule=self.sch,
                organisation=self.user.organisation,
                status=status,
                start=start_slot,
                end=end_slot,
            )
            slot.save()
            assert start_date_str in g.exception.messages

    def test_slot_end_historical_dates(self):
        """Test to validate slots dates.

        Ensure that dates are saved with valid dates.
        """
        start_slot = timezone.now() + timezone.timedelta(50)
        end_slot = timezone.now() - timezone.timedelta(10)
        status = SLOT_STATUS.BUSY
        end_start_str = "Slot end date must be greater than current date"

        with pytest.raises(ValidationError) as g:
            slot = Slot(
                schedule=self.sch,
                organisation=self.user.organisation,
                status=status,
                start=start_slot,
                end=end_slot,
                created_by=self.user.pk,
                updated_by=self.user.pk,
            )
            slot.save()
            assert end_start_str in g.exception.messages

    def test_period_greater_than_threshold(self):
        """Test to validate slot end date > start date."""
        status = SLOT_STATUS.BUSY

        slot = Slot(
            schedule=self.sch,
            organisation=self.user.organisation,
            status=status,
            start=self.start_date,
            end=self.end_date,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )

        slot.save()

    def test_period_less_than_threshold(self):
        """Test to validate if end date < start date."""
        slot_start = timezone.now() + timezone.timedelta(500)
        slot_end = slot_start + timezone.timedelta(minutes=2)
        status = SLOT_STATUS.BUSY

        with pytest.raises(ValidationError) as g:
            slot = Slot(
                schedule=self.sch,
                organisation=self.user.organisation,
                status=status,
                start=slot_start,
                end=slot_end,
            )
            slot.save()
            error_msg = {"end": "Slot period must 5 min or more"}
            assert error_msg in g.exception.messages

    def test_slot_within_end_less_than_start(self):
        """Test to validate if end date < start.

        Test if the end date is less than start date within the schedule.
        """
        slot_start = parse_datetime("2015-11-01T10:20:30.647504Z")
        slot_end = parse_datetime("2015-01-01T10:20:30.647504Z")

        sch = baker.make(
            Schedule,
            slot_duration=30,
            organisation=self.user.organisation,
        )
        status = SLOT_STATUS.BUSY
        with pytest.raises(ValidationError) as g:
            slot = Slot(
                schedule=sch,
                organisation=self.user.organisation,
                status=status,
                start=slot_start,
                end=slot_end,
            )
            slot.save()
            error_msg_end = {
                "end": "Slot end date must fall within selected schedule time"
            }
            assert error_msg_end in g.exception.messages

    def test_slot_within_schedule_end_lesser(self):
        """Test to validate end date.

        End date must end lesser than the schedule date.
        That is it tests if within the schedule date,
        that the end date is less than schedule end date.
        """
        slot_start = timezone.now() + timezone.timedelta(110)
        slot_end = slot_start + timezone.timedelta(100)

        sch = baker.make(
            Schedule,
            slot_duration=30,
            organisation=self.user.organisation,
        )
        status = SLOT_STATUS.BUSY
        slot = Slot(
            schedule=sch,
            organisation=self.user.organisation,
            status=status,
            start=slot_start,
            end=slot_end,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        slot.save()

    def test_slot_within_schedule_save(self):
        """Test to ensure valid slots saved.

        Ensure that only valid slots are saved, by
        running validations when saving slots.
        """
        slot_start = timezone.now() + timezone.timedelta(110)
        slot_end = slot_start + timezone.timedelta(100)

        sch = baker.make(
            Schedule,
            slot_duration=30,
            organisation=self.user.organisation,
        )
        status = SLOT_STATUS.BUSY
        slot = Slot(
            schedule=sch,
            organisation=self.user.organisation,
            status=status,
            start=slot_start,
            end=slot_end,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        slot.save()

    def test_slot_duration_invalid_length(self):
        """Test invalid slot duration."""
        with pytest.raises(ValidationError, match="Slot size must be a divisor of 60"):
            baker.make(
                Schedule,
                slot_duration=17,
                organisation=self.user.organisation,
            )

    def test_slot_duration_invalid_length_for_checkin(self):
        """Test invalid slot duration."""
        with pytest.raises(
            ValidationError,
            match="Slot size for a facility must set to a day in minutes",
        ):
            baker.make(
                Schedule,
                actor="FACILITY",
                slot_duration="240",
                specialty="OTHER",
                organisation=self.user.organisation,
            )


@pytest.mark.usefixtures("default_transactional_sender")
class AppointmentTest(LoggedInMixin):
    """Test the appointments."""

    def setUp(self):
        """Test appointments.

        Test to ensure Appointments hold healthcare event bookings
        which contains events amongst patient(s), practitioner(s),
        related person(s) and/or device(s) for a specific date
        or time.
        """
        super().setUp()
        self.start_date = timezone.now() + timezone.timedelta(hours=5)
        self.end_date = self.start_date + timezone.timedelta(minutes=30)

        self.start_date_less = self.start_date - timezone.timedelta(hours=1)
        self.end_date_more = timezone.now() + timezone.timedelta(hours=10)

        self.sch = baker.make(
            Schedule,
            description="Dr. Jane Doe",
            specialty="GENERAL PRACTITIONER",
            slot_duration=15,
            organisation=self.user.organisation,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        self.slot = baker.make(
            Slot,
            schedule=self.sch,
            organisation=self.user.organisation,
            start=self.start_date,
            end=self.end_date,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        self.checkin_sch = baker.make(
            Schedule,
            description="Check-in Queue",
            specialty="OTHER",
            actor="FACILITY",
            slot_duration=1439,
            organisation=self.user.organisation,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        self.checkin_slot = baker.make(
            Slot,
            schedule=self.checkin_sch,
            organisation=self.user.organisation,
            start=self.start_date,
            end=self.end_date,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        self.checkin_slot2 = baker.make(
            Slot,
            schedule=self.checkin_sch,
            organisation=self.user.organisation,
            start=timezone.now() + timezone.timedelta(days=1),
            end=timezone.now() + timezone.timedelta(days=2),
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        self.patient = baker.make(
            Patient,
            person__first_name="John",
            person__last_name="Doe",
            organisation=self.user.organisation,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        self.default_transactional_sender = SenderID.objects.filter(
            name="BeWellApp"
        ).latest("created")

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_sms_after_appointment_creation(self, mock_send_sms):
        """Test sending SMS after creation of an appointment."""
        local_tz = pytz.timezone(settings.TIME_ZONE)
        start = self.start_date.astimezone(local_tz)
        date_str = start.strftime("%a %b-%d")
        time_slot = start.strftime("%-I:%M%p")
        priority = settings.CELERY_TASK_MEDIUM_PRIORITY
        baker.make(
            PersonContact,
            person=self.patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )
        appt = baker.make(
            Appointment,
            start=self.start_date,
            end=self.end_date,
            slot=self.slot,
            organisation=self.user.organisation,
            patient=self.patient,
            appointment_status="BOOKED",
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )

        appt.refresh_from_db()
        # ensure the function to send sms is called
        expected_args = (
            "APPOINTMENT_CREATION",
            "+254712345678",
            self.global_organisation,
            self.patient.person,
            priority,
            date_str,
            time_slot,
            None,
            self.global_organisation.slade_code,
        )
        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=expected_args[4],
            args=(
                "APPOINTMENT_CREATION",
                (
                    f"Dear {self.patient.person.first_name}, an appointment for "
                    f"General Practitioner on {date_str} {time_slot} has been "
                    f"created at {self.user.organisation.organisation_name}"
                ),
                ["+254712345678"],
                self.user.organisation.slade_code,
                appt.branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_sms_after_checkin_appointment_creation(self, mock_send_sms):
        """Test SMS not sent after creation of a check-in for current day."""
        baker.make(
            PersonContact,
            person=self.patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )
        apt = baker.make(
            Appointment,
            start=self.start_date,
            end=self.end_date,
            slot=self.checkin_slot,
            organisation=self.user.organisation,
            patient=self.patient,
            appointment_status="BOOKED",
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        result = apt._send_appointment_message("CHECK_IN_CREATION")
        assert result == (None, "SMS are not sent for check-in appts for current day")
        mock_send_sms.assert_not_called()

    def test_checkin_appointment_creation_validation_with_booked_status(self):
        """Test checkin appointment creation validation for the same patient."""
        with pytest.raises(
            ValidationError, match="Patient already has an appointment for this slot."
        ):
            baker.make(
                Appointment,
                start=self.start_date,
                end=self.end_date,
                slot=self.checkin_slot,
                organisation=self.user.organisation,
                patient=self.patient,
                appointment_status="BOOKED",
            )
            baker.make(
                Appointment,
                start=self.start_date,
                end=self.end_date,
                slot=self.checkin_slot,
                organisation=self.user.organisation,
                patient=self.patient,
                appointment_status="BOOKED",
            )

    def test_checkin_appointment_creation_validation_with_arrived_status(self):
        """Test checkin appointment creation validation for the same patient."""
        with pytest.raises(
            ValidationError, match="Patient already has an appointment for this slot."
        ):
            baker.make(
                Appointment,
                start=self.start_date,
                end=self.end_date,
                slot=self.checkin_slot,
                organisation=self.user.organisation,
                patient=self.patient,
                appointment_status="ARRIVED",
            )
            baker.make(
                Appointment,
                start=self.start_date,
                end=self.end_date,
                slot=self.checkin_slot,
                organisation=self.user.organisation,
                patient=self.patient,
                appointment_status="BOOKED",
            )

    def test_patient_already_has_appointment_for_slot(self):
        """Test checkin appointment creation validation for the same patient."""
        with pytest.raises(
            ValidationError, match="Patient already has an appointment for this slot."
        ):
            baker.make(
                Appointment,
                start=self.start_date,
                end=self.end_date,
                slot=self.checkin_slot,
                organisation=self.user.organisation,
                patient=self.patient,
                appointment_status="PENDING",
            )
            baker.make(
                Appointment,
                start=self.start_date,
                end=self.end_date,
                slot=self.checkin_slot,
                organisation=self.user.organisation,
                patient=self.patient,
                appointment_status="PENDING",
            )

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_sms_after_checkin_gt_today_appointment_creation(self, mock_send_sms):
        """Test SMS sent after creation of a check-in for a day after today."""
        baker.make(
            PersonContact,
            person=self.patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )
        apt = baker.make(
            Appointment,
            start=timezone.now() + timezone.timedelta(days=1),
            end=timezone.now() + timezone.timedelta(days=1),
            slot=self.checkin_slot2,
            organisation=self.user.organisation,
            patient=self.patient,
            appointment_status="PENDING",
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        apt.refresh_from_db()
        local_tz = pytz.timezone(settings.TIME_ZONE)
        start = apt.start.astimezone(local_tz)
        date_str = start.strftime("%a %b-%d")
        priority = settings.CELERY_TASK_MEDIUM_PRIORITY
        mock_send_sms.assert_called_once_with(
            queue="advantage_tasks",
            priority=priority,
            args=(
                "CHECK_IN_CREATION",
                (
                    f"Hello, an appointment has been scheduled "
                    f"at {self.user.organisation.organisation_name} "
                    f"on {date_str}. "
                    f"In case of any concerns please call us on +254799999999."
                ),
                ["+254712345678"],
                self.user.organisation.slade_code,
                apt.branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_sms_after_appointment_rescheduling(self, mock_send_sms):
        """Test sending SMS after an appointment is rescheduled."""
        baker.make(
            PersonContact,
            person=self.patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )
        appt = baker.make(
            Appointment,
            start=self.start_date,
            end=self.end_date,
            slot=self.slot,
            organisation=self.user.organisation,
            patient=self.patient,
            appointment_status="BOOKED",
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )

        new_start = timezone.now() + timezone.timedelta(hours=5, days=1)
        new_end = self.start_date + timezone.timedelta(minutes=30, days=1)

        new_slot = baker.make(
            Slot,
            schedule=self.sch,
            organisation=self.user.organisation,
            start=new_start,
            end=new_end,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        appt.slot = new_slot
        appt.start = new_slot.start
        appt.end = new_slot.end
        appt.save()

        local_tz = pytz.timezone(settings.TIME_ZONE)
        start = new_slot.start.astimezone(local_tz)
        date_str = start.strftime("%a %b-%d")
        time_slot = start.strftime("%-I:%M%p")

        appt.refresh_from_db()
        mock_send_sms.assert_called_with(
            queue="advantage_tasks",
            priority=5,
            args=(
                "APPOINTMENT_RESCHEDULE",
                "Dear John, we would like to inform you that your appointment "
                "for General Practitioner at Demo Hospital has been rescheduled to "
                f"{date_str} {time_slot}. "
                "In case of any concerns please call us on +254799999999.",
                ["+254712345678"],
                self.global_organisation.slade_code,
                appt.branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )
        assert len(appt.pending_reminders) == 1
        self.assertAlmostEqual(
            appt.pending_reminders[0],
            appt.start,
            delta=timedelta(days=1, seconds=10),
        )

    @override_settings(ENVIRONMENT="prod")
    @patch("sil_advantage.notifications.sms.tasks.send_sms.apply_async")
    def test_send_sms_after_appointment_cancellation(self, mock_send_sms):
        """Test sending SMS after an appointment is cancelled."""
        baker.make(
            PersonContact,
            person=self.patient.person,
            contact_type="phone_number",
            contact="+254712345678",
        )
        appt = baker.make(
            Appointment,
            start=self.start_date,
            end=self.end_date,
            slot=self.slot,
            organisation=self.user.organisation,
            patient=self.patient,
            appointment_status="BOOKED",
            branch_id="abf685c2-9cc5-4d17-aa81-9944a0f590fa",
        )
        assert appt.slot.status == SLOT_STATUS.BUSY

        appt.appointment_status = "CANCELLED"
        appt.save()

        local_tz = pytz.timezone(settings.TIME_ZONE)
        start = self.start_date.astimezone(local_tz)
        date_str = start.strftime("%a %b-%d")
        time_slot = start.strftime("%-I:%M%p")
        mock_send_sms.assert_called_with(
            queue="advantage_tasks",
            priority=5,
            args=(
                "APPOINTMENT_CANCELLATION",
                "Dear John, due to unavoidable circumstances, "
                "we regret to inform you that your General Practitioner appointment "
                f"at Demo Hospital on {date_str} {time_slot} has been cancelled",
                ["+254712345678"],
                self.global_organisation.slade_code,
                appt.branch_id,
                None,
            ),
            kwargs={"sender_id": self.default_transactional_sender.id},
        )
        appt.refresh_from_db()
        assert appt.slot.status == SLOT_STATUS.FREE
        assert len(appt.pending_reminders) == 0

        # test idempotency
        mock_send_sms.reset_mock()
        appt.appointment_status = "CANCELLED"
        appt.save()
        mock_send_sms.assert_not_called()
        appt.refresh_from_db()
        assert appt.slot.status == SLOT_STATUS.FREE
        assert len(appt.pending_reminders) == 0

    def test_validate_start_historical_dates(self):
        """Test start date for the appointment.

        Validate that start date is greater than current.
        """
        appointment_status = APPOINTMENT_STATUS.BOOKED
        appointment_start_date = timezone.now() - timezone.timedelta(20)
        reason = "92716637"

        with pytest.raises(ValidationError) as g:
            appointment = Appointment(
                reason=reason,
                description="needs spectacles",
                start=appointment_start_date,
                end=self.end_date,
                slot=self.slot,
                appointment_status=appointment_status,
                organisation=self.user.organisation,
                created_by=self.user.pk,
                updated_by=self.user.pk,
                patient=self.patient,
            )
            appointment.save()
            error_msg_start_date = {
                "start": "Start date must be greater than current time"
            }
            assert error_msg_start_date in g.exception.messages

    def test_validate_end_historical_dates(self):
        """Test end date for appointment.

        Validate end date is greater than appointment end date.
        """
        appointment_status = APPOINTMENT_STATUS.BOOKED
        appointment_end_date = timezone.now() - timezone.timedelta(40)
        reason = "92716637"

        with pytest.raises(ValidationError) as g:
            appointment = Appointment(
                reason=reason,
                description="needs spectacles",
                start=self.start_date,
                end=appointment_end_date,
                slot=self.slot,
                appointment_status=appointment_status,
                organisation=self.user.organisation,
                created_by=self.user.pk,
                updated_by=self.user.pk,
                patient=self.patient,
            )
            appointment.save()
            error_msg_end_date = {
                "end": "Appointment end date must be greater than current time"
            }
            assert error_msg_end_date in g.exception.messages

    def test_validate_appointment_success(self):
        """Test to validate successful booking."""
        reason = "235146277"
        kwargs = {
            "reason": reason,
            "description": "needs spectacles",
            "start": self.start_date,
            "end": self.end_date,
            "slot": self.slot,
            "organisation": self.user.organisation,
            "created_by": self.user.pk,
            "updated_by": self.user.pk,
        }
        appointment = baker.make(Appointment, **kwargs)
        self.assertTrue(appointment)

        assert str(appointment) == reason

    def test_validate_appointment_fail_due_to_start_date(self):
        """Test to validate appointment fail.

        Ensure that appointment fails if the start date does not
        fall within selected slot duration.
        """
        appointment_status = APPOINTMENT_STATUS.BOOKED
        reason = "92716637"

        with pytest.raises(ValidationError) as g:
            appointment = Appointment(
                reason=reason,
                description="needs spectacles",
                start=self.start_date_less,
                end=self.end_date,
                slot=self.slot,
                appointment_status=appointment_status,
                organisation=self.user.organisation,
                created_by=self.user.pk,
                updated_by=self.user.pk,
                patient=self.patient,
            )
            appointment.save()
            error_msg_appointment_start = {
                "start": "Appointment start date must fall within\
                                selected slot duration"
            }
            assert error_msg_appointment_start in g.exception.messages

    def test_validate_appointment_fail_due_to_end_date(self):
        """Test to validate fail of appointment.

        Ensure appointment fails if end date does
        not fall within the selected slot duration.
        """
        appointment_status = APPOINTMENT_STATUS.BOOKED
        reason = "92716637"

        with pytest.raises(ValidationError) as g:
            appointment = Appointment(
                reason=reason,
                description="need spectacles",
                start=self.start_date,
                end=self.end_date_more,
                slot=self.slot,
                appointment_status=appointment_status,
                organisation=self.user.organisation,
                created_by=self.user.pk,
                updated_by=self.user.pk,
                patient=self.patient,
            )
            appointment.save()
            error_msg_appointment_end = {
                "end": "Appointment end date must fall within\
                                selected slot duration"
            }
            assert error_msg_appointment_end in g.exception.messages

    def test_booking_busy_slot(self):
        """Test overbooking a slot."""
        slot = baker.make(
            Slot,
            schedule=self.sch,
            organisation=self.user.organisation,
            start=self.start_date,
            end=self.end_date,
            created_by=self.user.pk,
            updated_by=self.user.pk,
            status=SLOT_STATUS.BUSY,
        )
        with pytest.raises(ValidationError, match="Slot is already booked."):
            appointment = Appointment(
                start=self.start_date,
                end=self.end_date,
                slot=slot,
                organisation=self.user.organisation,
                created_by=self.user.pk,
                updated_by=self.user.pk,
                patient=self.patient,
            )
            appointment.save()


class ParticipantTest(LoggedInMixin):
    """Test participants."""

    def setUp(self):
        """Test the format of start and end dates."""
        super().setUp()
        self.start_date = timezone.now() + timezone.timedelta(500)
        self.end_date = self.start_date + timezone.timedelta(7000)

    def test_unicode(self):
        """Test for the Participant model.

        Testing the `__str__` method.
        """
        appointment_status = APPOINTMENT_STATUS.BOOKED
        status = SLOT_STATUS.FREE
        reason = "1672672"

        schedule = baker.make(
            Schedule,
            slot_duration=30,
            created_by=self.user.pk,
            updated_by=self.user.pk,
            organisation=self.user.organisation,
        )
        slot = Slot(
            schedule=schedule,
            start=self.start_date,
            end=self.end_date,
            status=status,
            organisation=self.user.organisation,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        slot.save()
        patient = baker.make(
            Patient,
            organisation=self.user.organisation,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        appointment = Appointment(
            reason=reason,
            description="needs spectacles",
            start=self.start_date,
            end=self.end_date,
            slot=slot,
            appointment_status=appointment_status,
            patient=patient,
            organisation=self.user.organisation,
            created_by=self.user.pk,
            updated_by=self.user.pk,
        )
        appointment.save()
