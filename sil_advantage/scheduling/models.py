"""Scheduling models."""
from datetime import time, timedelta
from typing import Any, Optional

import pytz
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from rest_framework.serializers import ValidationError
from sil_cacheable.orm import CacheableManager

from sil_advantage.common.models import (
    AbstractBase,
    AbstractTiming,
    OrgUnitIdsMixin,
    TransitionValidationMixin,
)
from sil_advantage.notifications.sms.utils import send_custom_sms
from sil_advantage.patients.models import Patient
from sil_advantage.practitioners.models import Practitioner
from sil_advantage.scheduling import (
    ACTOR_OPTIONS,
    APPOINTMENT_PRIORITY,
    APPOINTMENT_STATUS,
    APPOINTMENT_TYPE,
    PRACTITIONER_TYPES,
    SLOT_STATUS,
)
from sil_advantage.settings.models import OrganisationSetting

APPOINTMENT_STATUS_TRANSITION_GRAPH = {
    "PROPOSED": ["PENDING", "BOOKED", "CANCELLED"],
    "PENDING": ["BOOKED", "CANCELLED"],
    "BOOKED": ["ARRIVED", "CANCELLED", "NO_SHOW"],
    "ARRIVED": ["FULFILLED"],
    "FULFILLED": [],
    "CANCELLED": [],
    "NO_SHOW": [],
}


class Schedule(OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """Contains fields found in a Schedule."""

    actor = models.CharField(
        max_length=255,
        choices=ACTOR_OPTIONS.CHOICES,
        default=ACTOR_OPTIONS.PRACTITIONER,
    )
    specialty = models.CharField(
        max_length=255,
        choices=PRACTITIONER_TYPES,
        null=True,
        blank=True,
    )
    practitioner = models.ForeignKey(
        Practitioner,
        on_delete=models.PROTECT,
        related_name="practitioner_schedules",
        null=True,
        blank=True,
    )
    slot_duration = models.PositiveSmallIntegerField()  # in minutes
    description = models.TextField(null=True, blank=True)

    model_validators = ["validate_slot_duration"]

    objects: models.Manager["Schedule"] = CacheableManager()
    _related_serialized_models = ("common_practitioner",)

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass

    def __str__(self) -> str:
        """Represent schedules using their names and schedule types."""
        description = (
            self.practitioner.person.get_full_name() if self.practitioner else ""
        )
        specialty = self.practitioner.qualification if self.practitioner else ""
        return ("-".join([description, specialty])) if self.practitioner else ""

    @cached_property
    def availability(self) -> dict[str, list[dict[str, time]]]:
        """Group timings by day of week."""
        available_days: dict[str, list[dict[str, time]]] = {}
        for timing in self.timings.all():
            day = timing.day_of_week
            if day not in available_days:
                available_days[day] = []
            hours = {"start": timing.start, "end": timing.end}
            available_days[day].append(hours)

        for day in available_days:
            available_days[day].sort(key=lambda timing: timing["start"])
        return available_days

    def validate_slot_duration(self) -> int:
        """Validate the slot_duration."""
        if self.actor == ACTOR_OPTIONS.FACILITY and int(self.slot_duration) != 1439:
            raise ValidationError(
                _("Slot size for a facility must set to a day in minutes")
            )
        if self.actor != ACTOR_OPTIONS.FACILITY and 60 % int(self.slot_duration) != 0:
            raise ValidationError(_("Slot size must be a divisor of 60"))

        return self.slot_duration

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Automatically create associated queue."""
        # import's here due to circular dependency issues
        from sil_advantage.visits.models import Queue

        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            Queue.objects.create(
                name=f"{self.description} | {self.specialty}"[:255],
                queue_type="CONSULTATION",
                schedule=self,
                organisation=self.organisation,
                created_by=self.created_by,
                updated_by=self.updated_by,
                cluster_id=self.cluster_id,
                branch_id=self.branch_id,
                department_id=self.department_id,
                workstation_id=self.workstation_id,
            )


class ScheduleTiming(AbstractTiming):
    """Describes the day to day & hourly availability for schedules."""

    schedule = models.ForeignKey(
        Schedule, on_delete=models.PROTECT, related_name="timings"
    )

    objects: models.Manager["ScheduleTiming"] = CacheableManager()


class Slot(OrgUnitIdsMixin, AbstractBase):  # type: ignore[django-manager-missing]
    """Contains fields for __slots__."""

    status = models.CharField(
        max_length=255,
        choices=SLOT_STATUS.CHOICES,
        default=SLOT_STATUS.FREE,
    )
    start = models.DateTimeField()
    end = models.DateTimeField()
    schedule = models.ForeignKey(
        Schedule,
        on_delete=models.PROTECT,
        related_name="schedule_slots",
    )

    organisation_verify = ["schedule"]

    model_validators = [
        "validate_historical_dates",
        "validate_slot_date",
        "validate_min_slot_length",
    ]

    objects: models.Manager["Slot"] = CacheableManager()
    _related_serialized_models = (
        "patients_patient",
        "scheduling_appointment",
    )

    class Meta(AbstractBase.Meta):
        """Set Slot options."""

        ordering = ("start",)

    def __str__(self) -> str:
        """Represent a slot by its start and end."""
        start_string = self.start.strftime("%Y-%m-%d %H:%MHrs")
        end_string = self.end.strftime("%Y-%m-%d %H:%MHrs")
        return " - ".join([start_string, end_string])

    @cached_property
    def is_busy(self) -> bool:
        """Infer slot busyness from number of appointments in the slot."""
        return self.status in ("BUSY", "BUSY_UNAVAILABLE", "BUSY_TENTATIVE")

    @cached_property
    def is_available(self) -> bool:
        """Infer when a slot is available by not being busy."""
        return not self.is_busy

    def validate_historical_dates(self) -> None:
        """Ensure that slots are saved with valid dates."""
        if self._state.adding:
            date_now = timezone.now()

            if date_now > self.start:
                raise ValidationError(
                    {
                        "start": [
                            _("Slot start date must be greater than current time"),
                        ],
                    }
                )
            if date_now > self.end:
                raise ValidationError(
                    {
                        "end": [
                            _("Slot end date must be greater than current time"),
                        ],
                    }
                )

    def validate_slot_date(self) -> None:
        """Ensure that the slot end date > start date."""
        if self.end < self.start:
            raise ValidationError(
                {"end": [_("End date must be greater than start date")]}
            )

    def validate_min_slot_length(self) -> None:
        """Ensure that slots are at least 10 minutes long."""
        time_difference = self.end - self.start
        difference_min = time_difference.total_seconds() / 60

        if difference_min < 5:
            raise ValidationError(_("Slot period must 5 min or more"))


class AppointmentTransitionLog(  # type: ignore[django-manager-missing]
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Hold appointment state transition logs."""

    appointment = models.ForeignKey(
        "Appointment",
        on_delete=models.PROTECT,
        related_name="state_transition_logs",
    )
    appointment_status = models.CharField(
        max_length=20, choices=APPOINTMENT_STATUS.CHOICES
    )
    appointment_status_from = models.CharField(
        max_length=20, choices=APPOINTMENT_STATUS.CHOICES
    )
    appointment_status_to = models.CharField(
        max_length=20, choices=APPOINTMENT_STATUS.CHOICES
    )

    class Meta(AbstractBase.Meta):
        """Set model options."""

        pass


class Appointment(  # type: ignore[django-manager-missing]
    TransitionValidationMixin,
    OrgUnitIdsMixin,
    AbstractBase,
):
    """Hold healthcare event bookings.

    A booking of a healthcare event among patient(s),
    practitioner(s), related person(s) and/or device(s)
    for a specific date/time.
    """

    appointment_status = models.CharField(
        max_length=255,
        choices=APPOINTMENT_STATUS.CHOICES,
        default=APPOINTMENT_STATUS.BOOKED,
    )
    appointment_type = models.CharField(
        max_length=255,
        choices=APPOINTMENT_TYPE.CHOICES,
        default=APPOINTMENT_TYPE.ROUTINE,
    )
    patient = models.ForeignKey(Patient, on_delete=models.PROTECT)
    reason = models.CharField(max_length=255, null=True, blank=True)
    cancellation_reason = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    description = models.CharField(max_length=255, null=True, blank=True)
    start = models.DateTimeField()
    end = models.DateTimeField()
    slot = models.ForeignKey(
        Slot,
        on_delete=models.PROTECT,
        related_name="slot_appointments",
    )
    pending_reminders = ArrayField(
        base_field=models.DateTimeField(),
        default=list,
        blank=True,
    )
    priority = models.CharField(
        max_length=255,
        choices=APPOINTMENT_PRIORITY.CHOICES,
        default=APPOINTMENT_PRIORITY.ROUTINE,
    )

    _transition_graph = APPOINTMENT_STATUS_TRANSITION_GRAPH
    _transition_field = "appointment_status"
    _transition_log_model = AppointmentTransitionLog
    _transition_log_model_fk_field = "appointment"

    organisation_verify = ["slot", "patient"]
    model_validators = [
        "validate_historical_dates",
        "validate_appointment",
        "validate_slot_availability",
    ]

    objects: models.Manager["Appointment"] = CacheableManager()
    _related_serialized_models = (
        "patients_patient",
        "scheduling_slot",
    )

    class Meta:
        """Upcoming appointments need to appear first."""

        ordering = ("-start",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Save old values of fields we're interested in."""
        super().__init__(*args, **kwargs)
        self._old_appointment_status = self.appointment_status
        self._old_slot_id = self.slot_id

    @property
    def reason_display(self) -> str:
        """Return a friendly appointment reason display."""
        return self.reason or "-"

    def __str__(self) -> str:
        """Represent an appointment using it's reason."""
        return self.reason_display.split(":")[-1]

    def validate_historical_dates(self) -> None:
        """Prevent saving of historical appointments."""
        if self._state.adding:
            date_now = timezone.now()

            if date_now > self.start:
                raise ValidationError(
                    {
                        "start_date": [
                            _("Start date must be greater than current time"),
                        ],
                    }
                )

            if date_now > self.end:
                raise ValidationError(
                    {
                        "end_date": [
                            _(
                                "Appointment end date must be greater\
                            than current time"
                            )
                        ]
                    }
                )

    def validate_appointment(self) -> None:
        """Validate appointment start and end."""
        appointment_slot = Slot.objects.get(pk=self.slot_id)
        slot_start = appointment_slot.start
        slot_end = appointment_slot.end
        appointment_start = self.start
        appointment_end = self.end

        if (slot_start > appointment_start) or (slot_end < appointment_start):
            raise ValidationError(
                {
                    "start": [
                        _(
                            "Appointment start date must fall within\
                                selected slot duration"
                        )
                    ]
                }
            )

        if (slot_start > appointment_end) or (slot_end < appointment_end):
            raise ValidationError(
                {
                    "end": [
                        _(
                            "Appointment end date must fall within\
                                selected slot duration"
                        )
                    ]
                }
            )

    def validate_slot_availability(self) -> None:
        """Validate availability of slot we're booking against."""
        check_in_query = Appointment.objects.filter(
            slot=self.slot, patient=self.patient
        )
        checkin_statuses = check_in_query.filter(
            Q(appointment_status="BOOKED")
            | Q(appointment_status="ARRIVED")
            | Q(appointment_status="PENDING")
        ).exists()
        if self._state.adding:
            if self.slot.schedule.actor != ACTOR_OPTIONS.FACILITY and self.slot.is_busy:
                raise ValidationError({"slot": [_("Slot is already booked.")]})
            if self.slot.schedule.actor == ACTOR_OPTIONS.FACILITY and checkin_statuses:
                raise ValidationError(
                    {"slot": [_("Patient already has an appointment for this slot.")]}
                )

    def _send_appointment_message(
        self, sms_intention: str
    ) -> tuple[Optional[dict[str, Any]], str]:
        """Send an appointment related SMS."""
        # Don't send any messages for check-in scheduled for current day
        today = timezone.now().date()
        start_date = self.start.date()
        if self.slot.schedule.actor == "FACILITY" and start_date == today:
            return None, "SMS are not sent for check-in appts for current day"

        phone_number = self.patient.person.phone_number
        org = self.organisation
        branch_id = self.branch_id
        specialty = self.slot.schedule.specialty
        priority = settings.CELERY_TASK_MEDIUM_PRIORITY

        if phone_number:
            local_tz = pytz.timezone(settings.TIME_ZONE)
            start = self.start.astimezone(local_tz)
            send_custom_sms(
                sms_intention,
                phone_number,
                org,
                branch_id,
                self.patient.person,
                priority,
                date=start.strftime("%a %b-%d"),
                time_slot=start.strftime("%-I:%M%p"),
                org_phone_number=org.phone_number,
                specialty=specialty.title() if specialty else None,
                department_id=self.department_id,
                workstation_id=self.workstation_id,
            )
        return None, "SMS sent successfully"

    def send_appointment_creation_message(
        self,
    ) -> tuple[Optional[dict[str, Any]], str]:
        """Send an SMS after appoinment creation."""
        return self._send_appointment_message("APPOINTMENT_CREATION")

    def send_check_in_creation_message(
        self,
    ) -> tuple[Optional[dict[str, Any]], str]:
        """Send checkin creation sms for check-ins greater than today."""
        return self._send_appointment_message("CHECK_IN_CREATION")

    def send_appointment_reminder_message(
        self,
    ) -> tuple[Optional[dict[str, Any]], str]:
        """Send an appointment reminder SMS."""
        return self._send_appointment_message("APPOINTMENT_REMINDER")

    def send_appointment_rescheduling_message(
        self,
    ) -> tuple[Optional[dict[str, Any]], str]:
        """Send an SMS after a reschedule."""
        return self._send_appointment_message("APPOINTMENT_RESCHEDULE")

    def send_appointment_cancellation_message(
        self,
    ) -> tuple[Optional[dict[str, Any]], str]:
        """Send an SMS after an appointment is cancelled."""
        return self._send_appointment_message("APPOINTMENT_CANCELLATION")

    def _update_pending_reminders(self) -> None:
        """Update the pending appointment reminders."""
        self.pending_reminders = []
        setting = OrganisationSetting.get_setting(
            self.organisation,
            self.branch_id,
            "scheduling:appointment_reminder_timings",
        )
        now = timezone.now()
        for hours_before in setting.value:
            reminder_time = self.start - timedelta(hours=hours_before)
            if reminder_time > now:
                self.pending_reminders.append(reminder_time)

    @transaction.atomic
    def save(self, *args: Any, **kwargs: Any) -> None:
        """Send appointment creation message for new appointments."""
        is_new = self._state.adding and self.slot.schedule.actor != "FACILITY"
        appt_cancelled = (
            self._old_appointment_status != self.appointment_status
            and self.appointment_status == "CANCELLED"
        )
        today = timezone.now().date()
        start_date = self.start.date()

        if is_new or self._old_slot_id != self.slot_id:
            self._update_pending_reminders()
        elif appt_cancelled:
            self.pending_reminders = []
        self.pending_reminders.sort()
        super().save(*args, **kwargs)

        if is_new:
            self.slot.status = SLOT_STATUS.BUSY
            self.slot.save(update_fields=["status"])
            self.send_appointment_creation_message()
        elif self.slot.schedule.actor == "FACILITY" and start_date > today:
            self.send_check_in_creation_message()
        elif appt_cancelled:
            self.slot.status = SLOT_STATUS.FREE
            self.slot.save(update_fields=["status"])
            self.send_appointment_cancellation_message()

        elif self._old_slot_id != self.slot_id:
            # free up old slot
            _old_slot = Slot.objects.get(pk=self._old_slot_id)
            _old_slot.status = SLOT_STATUS.FREE
            _old_slot.save(update_fields=["status"])
            # mark new slot as busy
            self.slot.status = SLOT_STATUS.BUSY
            self.slot.save(update_fields=["status"])
            self.send_appointment_rescheduling_message()
        self._old_appointment_status = self.appointment_status
        self._old_slot_id = self.slot_id
