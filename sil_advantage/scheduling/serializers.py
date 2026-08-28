"""Scheduling serializers."""
from typing import Any

from rest_framework import serializers

from sil_advantage.common.serializers import BaseSerializer
from sil_advantage.common.serializers.common_serializers import (
    PractitionerSerializer,
)
from sil_advantage.patients.serializers import PatientSerializer
from sil_advantage.scheduling.models import (
    Appointment,
    AppointmentTransitionLog,
    Schedule,
    ScheduleTiming,
    Slot,
)


class ScheduleSerializer(BaseSerializer):
    """Serialize schedules."""

    availability = serializers.ReadOnlyField()
    queue = serializers.UUIDField(read_only=True)
    practitioner_data = PractitionerSerializer(read_only=True, source="practitioner")

    class Meta:
        """Serializer options."""

        model = Schedule
        fields = "__all__"


class ScheduleTimingSerializer(BaseSerializer):
    """Serialize schedule timings."""

    class Meta:
        """Serializer options."""

        model = ScheduleTiming
        fields = "__all__"


class AppointmentTransitionLogSerializer(BaseSerializer):
    """AppointmentTransitionLog Serializer."""

    class Meta:
        """Serialization options."""

        model = AppointmentTransitionLog
        fields = "__all__"


class AppointmentSerializer(BaseSerializer):
    """Serialize appointments."""

    reason_display = serializers.ReadOnlyField()
    patient_details = PatientSerializer(
        read_only=True,
        source="patient",
    )
    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    sched_specialty = serializers.ReadOnlyField(
        source="slot.schedule.specialty",
    )
    sched_description = serializers.ReadOnlyField(
        source="slot.schedule.description",
    )
    sched_id = serializers.ReadOnlyField(
        source="slot.schedule_id",
    )
    sched_actor = serializers.ReadOnlyField(
        source="slot.schedule.actor",
    )
    pending_reminders = serializers.ListField(read_only=True)

    class Meta:
        """Serializer options."""

        model = Appointment
        fields = "__all__"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Make sure the appointment time always matches the slot's.

        The exception being the check-in schedule.
        """
        slot = self.validated_data.get("slot")
        if slot and slot.schedule.actor != "FACILITY":
            self.validated_data["start"] = slot.start
            self.validated_data["end"] = slot.end
        super().save(*args, **kwargs)


class SlotSerializer(BaseSerializer):
    """Serialize schedule slots."""

    status_display = serializers.ReadOnlyField()
    is_busy = serializers.ReadOnlyField()
    is_available = serializers.ReadOnlyField()

    class Meta:
        """Serializer options."""

        model = Slot
        fields = "__all__"
